"""The undo store: a change offers the stored inverse of itself, the app claims it once.

A module registers a handler per kind in its `provide` and calls `offer` after a write; the route
`POST /api/undo/{token}` calls `undo`. The entry is data (a kind and a JSON payload), not a
closure, so it survives a restart. Claiming deletes it in a committed unit of its own, so a second
click, a double request or an expired token finds nothing; the handler then runs in its own unit,
and the entry stays consumed when the handler refuses.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import GoneError
from code_factory.undo.models import Changed, UndoHandler
from code_factory.undo.repository import UndoRepository
from code_factory.undo.rules import expires_at, new_token, sweep_cutoff, undo_live

GONE = "nothing to undo any more"
SWEEP_INTERVAL = 60.0
logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """The service's default clock."""
    return datetime.now(UTC)


def _check_kind(kind: str) -> None:
    if not kind:
        msg = "an undo kind is not blank"
        raise ValueError(msg)


class UndoService:
    """Offers, claims and sweeps undo entries."""

    def __init__(self, uow: UnitOfWork, clock: Callable[[], datetime] = utc_now) -> None:
        self._uow = uow
        self._clock = clock
        self._handlers: dict[str, UndoHandler] = {}

    def register(self, kind: str, handler: UndoHandler) -> None:
        """Say how `kind` is taken back; a kind has one handler, so a second is a bug."""
        _check_kind(kind)
        if kind in self._handlers:
            msg = f"undo kind {kind} is registered already"
            raise ValueError(msg)
        self._handlers[kind] = handler

    async def offer(self, kind: str, payload: dict[str, Any], notice: str) -> Changed:
        """Store the inverse of a change for 30 seconds; the answer carries its token."""
        _check_kind(kind)
        if kind not in self._handlers:
            msg = f"undo kind {kind} has no handler"
            raise ValueError(msg)
        token = new_token()
        async with self._uow() as session:
            await session.connection()  # the window starts once the connection is held
            now = self._clock()
            await UndoRepository(session).insert(token, kind, payload, now, expires_at(now))
        return Changed(notice=notice, undo=token)

    async def undo(self, token: str, by: str) -> Changed:
        """Take the change back once; `GoneError` when the token is used, expired or unknown."""
        async with self._uow() as session:
            await session.connection()  # the window is read once the connection is held
            now = self._clock()
            entry = await UndoRepository(session).claim(token)
            claimed = None if entry is None else (entry.kind, entry.payload, entry.expires_at)
        if claimed is None:
            raise GoneError(GONE)
        kind, payload, expiry = claimed
        handler = self._handlers.get(kind)
        if handler is None or not undo_live(expiry, now):
            raise GoneError(GONE)
        await handler(payload, by)
        return Changed(notice="", undo=None)

    async def sweep(self) -> int:
        """Delete the entries expired for more than a minute; how many went."""
        async with self._uow() as session:
            return await UndoRepository(session).sweep(sweep_cutoff(self._clock()))

    async def run_sweeper(self, interval: float = SWEEP_INTERVAL) -> None:
        """Sweep every `interval` seconds until cancelled; a failed pass is logged, not fatal.

        Expiry is enforced when an entry is claimed, so this only keeps the table small.
        """
        while True:
            try:
                await self.sweep()
            except Exception:
                logger.exception("undo sweep failed")
            await asyncio.sleep(interval)
