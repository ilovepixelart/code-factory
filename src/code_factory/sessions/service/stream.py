"""The event stream: every captured event past a position, then each new one.

Readers are woken by the Postgres notification the ingest sends. A fallback read every few
seconds covers a notification lost with its connection, and a keepalive frame tells a quiet
client the stream lives.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from code_factory.platform.db import UnitOfWork
from code_factory.sessions.repository import LedgerRepository
from code_factory.sessions.rules.stream import KEEPALIVE, sse_frame
from code_factory.sessions.service.common import STREAM_BATCH


@dataclass(frozen=True, slots=True)
class StreamTiming:
    """How long a stream waits before it reads without a notification, or says it is alive."""

    fallback_s: float = 5.0
    keepalive_s: float = 15.0


async def wait_for_any(events: list[asyncio.Event], within_s: float) -> None:
    """Return when any of the events is set or `within_s` seconds pass."""
    waiters = [asyncio.create_task(event.wait()) for event in events]
    try:
        await asyncio.wait(waiters, timeout=within_s, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for waiter in waiters:
            waiter.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)


class StreamHub:
    """The open streams of this process and what wakes them."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        timing: StreamTiming | None = None,
        batch: int = STREAM_BATCH,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._uow = uow
        self._timing = timing or StreamTiming()
        self._batch = batch
        self._monotonic = monotonic
        self._subscribers: set[asyncio.Event] = set()
        self._closing = asyncio.Event()

    @property
    def open_streams(self) -> int:
        """How many streams are open now."""
        return len(self._subscribers)

    def wake(self) -> None:
        """Make every open stream read now."""
        for subscriber in self._subscribers:
            subscriber.set()

    def shutdown(self) -> None:
        """End every open stream."""
        self._closing.set()
        self.wake()

    async def stream(self, after: int, stop: asyncio.Event) -> AsyncIterator[str]:
        """The frames of every event past `after`; ends when `stop` is set or the hub shuts down."""
        woken = asyncio.Event()
        self._subscribers.add(woken)
        last = after
        quiet_since = self._monotonic()
        try:
            while not stop.is_set() and not self._closing.is_set():
                woken.clear()  # before the read: a notification during it is kept
                async with self._uow() as session:
                    events = await LedgerRepository(session).events_after(last, self._batch)
                for event in events:
                    yield sse_frame(event)
                    last = event.seq
                if events:
                    quiet_since = self._monotonic()
                    continue
                silent = self._monotonic() - quiet_since
                if silent >= self._timing.keepalive_s:
                    yield KEEPALIVE
                    quiet_since = self._monotonic()
                    continue
                pause = min(self._timing.fallback_s, self._timing.keepalive_s - silent)
                await wait_for_any([woken, stop], pause)  # shutdown wakes `woken`
        finally:
            self._subscribers.discard(woken)
