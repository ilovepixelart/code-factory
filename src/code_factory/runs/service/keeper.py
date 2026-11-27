"""The run keeper: the one background task of the runs module.

One interval after the start (the process is still starting) it settles what the previous process
left: runs that ended while the board was down, permission requests made before the keeper
started, whose waiters died. It then
collects every `interval` seconds and does the slower housekeeping every `housekeeping_every`. A
pass that fails is logged and the loop goes on; cancellation propagates. It never signals a run:
runs outlive the board by design.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Protocol

from code_factory.runs.models import Ended, PreviewRecord
from code_factory.runs.service.base import utc_now

logger = logging.getLogger(__name__)

INTERVAL_S = 2.0
HOUSEKEEPING_S = 30.0


class Collecting(Protocol):
    """The run service as the keeper uses it."""

    async def collect(self) -> list[Ended]:
        """One collection pass."""
        ...


class Requests(Protocol):
    """The permission service as the keeper uses it."""

    async def withdraw_pending(self, before: datetime) -> int:
        """End the requests made before `before`, whose waiters are gone."""
        ...

    async def expire(self, now: datetime) -> Sequence[object]:
        """Expire the requests that waited too long."""
        ...

    async def prune(self, now: datetime) -> int:
        """Delete the decisions past their retention."""
        ...


class Previews(Protocol):
    """The preview service as the keeper uses it."""

    async def running(self) -> list[PreviewRecord]:
        """The previews whose process runs; the rows of dead ones go."""
        ...


async def _guarded(what: str, work: Callable[[], Awaitable[object]]) -> None:
    try:
        await work()
    except Exception:
        logger.exception("the run keeper's %s failed", what)


async def run_keeper(  # noqa: PLR0913  # the three services and the two periods of one loop
    runs: Collecting,
    requests: Requests,
    previews: Previews,
    *,
    interval: float = INTERVAL_S,
    housekeeping_every: float = HOUSEKEEPING_S,
    clock: Callable[[], datetime] = utc_now,
) -> None:
    """Keep the runs until cancelled; the first pass comes one interval after the start."""
    started = clock()
    await asyncio.sleep(interval)
    await _guarded("recovery", lambda: requests.withdraw_pending(started))
    await _guarded("collection", runs.collect)
    every = max(1, round(housekeeping_every / interval))
    passes = 0
    while True:
        await asyncio.sleep(interval)
        passes += 1
        await _guarded("collection", runs.collect)
        if passes % every == 0:
            await _guarded("housekeeping", lambda: _housekeeping(requests, previews, clock))


async def _housekeeping(
    requests: Requests, previews: Previews, clock: Callable[[], datetime]
) -> None:
    now = clock()
    await requests.expire(now)
    await requests.prune(now)
    await previews.running()
