"""Moving the capture spool into the ledger and keeping each session's view current.

Reading and parsing happen outside any transaction. One short transaction per batch takes the
advisory lock, advances each spool's progress by compare-and-set, inserts the events and rejects,
rederives the touched sessions and sends `NOTIFY`. The lock is held through the commit so that
`seq` order is commit order.
"""

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import UnavailableError
from code_factory.sessions.adapters import CheckoutLocator, SpoolLine, SpoolReader
from code_factory.sessions.models import (
    Checkout,
    Event,
    IngestResult,
    NewEvent,
    Reject,
    SessionView,
)
from code_factory.sessions.repository import (
    CHANNEL,
    LedgerRepository,
    NewView,
    StoredView,
    ViewRepository,
)
from code_factory.sessions.rules import derive
from code_factory.sessions.rules.checkout import folder_name
from code_factory.sessions.rules.events import event_row, text_field, too_long

logger = logging.getLogger(__name__)

BATCH_LINES = 5000
HOT_SECONDS = 600.0
SWEEP_SECONDS = 30.0
LOCK_WAIT_MS = 5000
LOCK_BUSY = "another ingest holds the lock: try again in a moment"
WINDOW_CACHE = 256
PARSE_YIELD_EVERY = 500
MOVED_RETRIES = 3


@dataclass(frozen=True, slots=True)
class IngestOptions:
    """The limits of one ingester and the channel it notifies on."""

    batch_lines: int = BATCH_LINES
    lock_wait_ms: int = LOCK_WAIT_MS
    channel: str = CHANNEL


class _Moved(Exception):  # noqa: N818  # a signal, not a failure
    """Another ingester moved a spool's progress after this one read it."""


class _Busy(Exception):  # noqa: N818  # a signal, not a failure
    """Another ingester holds the lock."""


@dataclass(slots=True)
class _Batch:
    spools: dict[str, tuple[int, int]] = field(default_factory=dict)
    events: list[NewEvent] = field(default_factory=list)
    rejects: list[Reject] = field(default_factory=list)

    @property
    def lines(self) -> int:
        return len(self.events) + len(self.rejects)


@dataclass(slots=True)
class _Seen:
    size: int
    changed: float


@dataclass(frozen=True, slots=True)
class _Window:
    last_seq: int
    events: list[Event]


def _fallback(cwd: str) -> Checkout:
    return Checkout(folder_name(cwd), "")


class Ingester:
    """The spool to the ledger and the views."""

    def __init__(
        self,
        uow: UnitOfWork,
        spool: SpoolReader,
        locator: CheckoutLocator,
        *,
        options: IngestOptions | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._uow = uow
        self._spool = spool
        self._locator = locator
        self._options = options or IngestOptions()
        self._monotonic = monotonic
        self._seen: dict[str, _Seen] = {}
        self._swept = float("-inf")
        self._shrunk: dict[str, int] = {}
        self._windows: OrderedDict[str, _Window] = OrderedDict()

    async def ingest_once(self, *, wait: bool = False) -> IngestResult:
        """Take every new whole line of the spool into the ledger.

        Without `wait` a pass that finds another ingester holding the lock does nothing; with it
        the lock is waited for up to five seconds, `UnavailableError` says it never came, and a
        pass that loses a race to another ingester starts again.
        """
        totals = _Totals()
        for _ in range(MOVED_RETRIES if wait else 1):
            try:
                await self._pass(wait=wait, totals=totals)
            except _Moved:
                continue
            except _Busy:
                if wait:
                    raise UnavailableError(LOCK_BUSY) from None
                break
            else:
                break
        return IngestResult(totals.lines, totals.rejects, len(totals.sessions))

    async def _progress(self) -> dict[str, int]:
        async with self._uow() as session:
            return await LedgerRepository(session).progress()

    async def _pending(self, names: list[str], progress: dict[str, int]) -> list[tuple[str, int]]:
        """The spools with bytes past their progress, found by statting only the hot ones.

        Every spool is statted when first seen and in a sweep every 30 seconds; in between only
        those that changed in the last ten minutes.
        """
        now = self._monotonic()
        sweep = now - self._swept >= SWEEP_SECONDS
        if sweep:
            self._swept = now
        watched = [
            name
            for name in names
            if sweep or name not in self._seen or now - self._seen[name].changed < HOT_SECONDS
        ]
        stats = await self._spool.stats(watched)
        pending = []
        for name in watched:
            if name not in stats:
                continue
            size = stats[name][0]
            seen = self._seen.get(name)
            if seen is None or seen.size != size:
                self._seen[name] = _Seen(size, now)
            offset = progress.get(name, 0)
            if size > offset:
                pending.append((name, offset))
            elif size < offset and self._shrunk.get(name) != size:
                self._shrunk[name] = size
                logger.warning(
                    "spool %s is %d bytes, shorter than the %d already taken: it was replaced "
                    "and is not read again; remove its progress to take it from the start",
                    name,
                    size,
                    offset,
                )
        return pending

    async def _pass(self, *, wait: bool, totals: _Totals) -> None:
        names = await self._spool.names()
        if not names:
            return  # nothing to take: the database is not touched
        pending = await self._pending(names, await self._progress())
        batch = _Batch()
        for name, first in pending:
            offset = first
            while True:
                read = await self._spool.read_from(name, offset)
                if not read.lines:
                    break
                room = self._options.batch_lines - batch.lines
                taken = read.lines[:room]
                end = read.lines[room].offset if room < len(read.lines) else read.end
                await self._parse(name, taken, batch)
                batch.spools[name] = (batch.spools.get(name, (offset, offset))[0], end)
                offset = end
                if batch.lines >= self._options.batch_lines:
                    await self._commit(batch, wait=wait, totals=totals)
                    batch = _Batch()
        if batch.lines:
            await self._commit(batch, wait=wait, totals=totals)

    @staticmethod
    async def _parse(name: str, lines: Sequence[SpoolLine], batch: _Batch) -> None:
        for count, line in enumerate(lines, 1):
            row = (
                too_long(name, line.offset, line.data)
                if line.too_long
                else event_row(name, line.offset, line.data)
            )
            if isinstance(row, Reject):
                batch.rejects.append(row)
            else:
                batch.events.append(row)
            if count % PARSE_YIELD_EVERY == 0:
                await asyncio.sleep(0)

    async def _locate(self, batch: _Batch) -> dict[str, Checkout | None]:
        """Where the folders of the touched sessions are, asked before the transaction."""
        touched = sorted({event.session_id for event in batch.events})
        async with self._uow() as session:
            stored = await ViewRepository(session).get_many(touched)
        folders = {view.view.cwd for view in stored.values()}
        folders |= {
            cwd for event in batch.events if (cwd := text_field(event.payload, "cwd")) is not None
        }
        return {cwd: await self._locator.locate(cwd) for cwd in sorted(folders)}

    async def _commit(self, batch: _Batch, *, wait: bool, totals: _Totals) -> None:
        located = await self._locate(batch)
        async with self._uow() as session:
            ledger = LedgerRepository(session)
            if not await ledger.lock(wait_ms=self._options.lock_wait_ms if wait else None):
                raise _Busy
            if not await self._still_there(batch):
                raise _Moved
            for spool, (old, new) in batch.spools.items():
                if not await ledger.advance(spool, old=old, new=new):
                    raise _Moved
            stored = await ledger.insert_events(batch.events)
            await ledger.insert_rejects(batch.rejects)
            windows = await self._update_views(ledger, ViewRepository(session), stored, located)
            if stored:
                await ledger.notify(self._options.channel, stored[-1].seq)
        for session_id, window in windows.items():
            self._windows[session_id] = window
            self._windows.move_to_end(session_id)
        while len(self._windows) > WINDOW_CACHE:
            self._windows.popitem(last=False)
        totals.lines += batch.lines
        totals.rejects += len(batch.rejects)
        totals.sessions |= {event.session_id for event in stored}

    async def _still_there(self, batch: _Batch) -> bool:
        """Whether every spool of the batch still holds the bytes it was read from.

        Asked under the lock: a spool pruned since it was read is gone, and its lines must not
        come back as rows.
        """
        stats = await self._spool.stats(batch.spools)
        return all(
            name in stats and stats[name][0] >= new for name, (_, new) in batch.spools.items()
        )

    async def _window(
        self, ledger: LedgerRepository, session_id: str, row: StoredView | None
    ) -> list[Event]:
        if row is None:
            return []
        cached = self._windows.get(session_id)
        if cached is not None and cached.last_seq == row.last_seq:
            return cached.events
        events = await ledger.events_from(session_id, row.window_seq, upto=row.last_seq)
        return [derive.for_views(event) for event in events]

    async def _update_views(
        self,
        ledger: LedgerRepository,
        views: ViewRepository,
        stored: list[Event],
        located: dict[str, Checkout | None],
    ) -> dict[str, _Window]:
        by_session: dict[str, list[Event]] = {}
        for event in stored:
            by_session.setdefault(event.session_id, []).append(event)
        existing = await views.get_many(list(by_session))
        written: list[NewView] = []
        windows: dict[str, _Window] = {}
        for session_id, new in by_session.items():
            row = existing.get(session_id)
            carried = (row.view.cwd, row.view.transcript) if row else ("", "")
            window, carried = derive.extend_window(
                await self._window(ledger, session_id, row),
                carried,
                [derive.for_views(event) for event in new],
            )
            view = derive.derive_unsettled(window, carried)
            if view is None:  # a window of at least one new event always derives
                continue
            view = self._placed(view, located, row)
            written.append(NewView(view, window[-1].seq, window[0].seq, derive.RULES_VERSION))
            windows[session_id] = _Window(window[-1].seq, window)
        await views.upsert(written)
        return windows

    @staticmethod
    def _placed(
        view: SessionView, located: dict[str, Checkout | None], row: StoredView | None
    ) -> SessionView:
        if view.cwd not in located and row is not None and row.view.cwd == view.cwd:
            return view.model_copy(
                update={"repository": row.view.repository, "branch": row.view.branch}
            )
        place = located.get(view.cwd) or _fallback(view.cwd)
        return view.model_copy(update={"repository": place.repository, "branch": place.branch})

    def forget_windows(self, session_ids: Sequence[str]) -> None:
        """Drop the cached windows of sessions whose views were rewritten from their events."""
        for session_id in session_ids:
            self._windows.pop(session_id, None)


@dataclass(slots=True)
class _Totals:
    lines: int = 0
    rejects: int = 0
    sessions: set[str] = field(default_factory=set)
