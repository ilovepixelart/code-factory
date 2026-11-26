"""Deriving every session's view again from its events."""

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import UnavailableError
from code_factory.sessions.adapters import CheckoutLocator
from code_factory.sessions.models import Event, SessionView
from code_factory.sessions.repository import (
    LedgerRepository,
    NewView,
    ViewRepository,
)
from code_factory.sessions.rules import derive
from code_factory.sessions.rules.checkout import folder_name
from code_factory.sessions.service.ingest import LOCK_BUSY, LOCK_WAIT_MS, Ingester


def _window_start(events: list[Event]) -> int:
    starts = [event.seq for event in events if event.event == "SessionStart"]
    return starts[-1] if starts else events[0].seq


class Rebuilder:
    """Rederives views: after the rules change, or for sessions that have none."""

    def __init__(
        self,
        uow: UnitOfWork,
        locator: CheckoutLocator,
        ingest: Ingester,
        lock_wait_ms: int = LOCK_WAIT_MS,
    ) -> None:
        self._uow = uow
        self._locator = locator
        self._ingest = ingest
        self._lock_wait_ms = lock_wait_ms

    async def rebuild(self, *, batch: int, stale_only: bool) -> int:
        """Rederive the views, `batch` sessions at a time; how many.

        `stale_only` leaves the views written by the current rules alone.
        """
        async with self._uow() as session:
            views = ViewRepository(session)
            ids = (
                await views.stale_session_ids(derive.RULES_VERSION)
                if stale_only
                else await views.session_ids()
            )
        for start in range(0, len(ids), batch):
            await self._rebuild_batch(ids[start : start + batch])
        return len(ids)

    async def _rebuild_batch(self, ids: list[str]) -> None:
        built: list[NewView] = []
        async with self._uow() as session:
            ledger = LedgerRepository(session)
            for session_id in ids:
                events = await ledger.events_from(session_id)
                view = derive.derive_unsettled([derive.for_views(e) for e in events])
                if view is not None:
                    last, start = events[-1].seq, _window_start(events)
                    built.append(NewView(view, last, start, derive.RULES_VERSION))
        placed = [await self._placed(item) for item in built]
        async with self._uow() as session:
            ledger = LedgerRepository(session)
            if not await ledger.lock(wait_ms=self._lock_wait_ms):
                raise UnavailableError(LOCK_BUSY)
            # A session the ingest moved on, or pruning removed, since it was read is left alone.
            latest = await ledger.latest_seqs([item.view.session_id for item in placed])
            await ViewRepository(session).upsert(
                [item for item in placed if latest.get(item.view.session_id) == item.last_seq]
            )
        self._ingest.forget_windows(ids)

    async def _placed(self, item: NewView) -> NewView:
        place = await self._locator.locate(item.view.cwd)
        repository = place.repository if place else folder_name(item.view.cwd)
        branch = place.branch if place else ""
        view: SessionView = item.view.model_copy(
            update={"repository": repository, "branch": branch}
        )
        return NewView(view, item.last_seq, item.window_seq, item.rules_version)
