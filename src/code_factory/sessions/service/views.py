"""The reads that answer what sessions are doing, from the stored views and the ledger."""

from datetime import datetime, timedelta

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import NotFoundError
from code_factory.platform.text import Paging
from code_factory.sessions.models import AtWork, JsonAnswer, SessionView, StateFilter
from code_factory.sessions.repository import LedgerRepository, ViewRepository, to_datetime
from code_factory.sessions.rules import timeline as rules_timeline
from code_factory.sessions.rules.at_work import subagents_at_work
from code_factory.sessions.rules.page import page_json, session_json
from code_factory.sessions.rules.settle import ENDED_AFTER_SECONDS, ordered, settled
from code_factory.sessions.service.common import Clock

DEFAULT_LAST = 500


def _cutoff(now: float) -> datetime:
    """The moment before which a working or idle session has ended by the clock."""
    return to_datetime(now) - timedelta(seconds=ENDED_AFTER_SECONDS)


class ViewReader:
    """Sessions as the Sessions page, the board and the team read them."""

    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    def _now(self) -> float:
        return self._clock().timestamp()

    async def list_sessions(
        self, paging: Paging | None, *, ended: bool = False, state: StateFilter | None = None
    ) -> JsonAnswer:
        """The Sessions list: every session unpaged, or one page of it.

        A page reads only the rows not ended by the clock (a small set) unless `ended` asks for
        them; how many it leaves out comes from a count.
        """
        now = self._now()
        cutoff = _cutoff(now)
        hidden = 0
        async with self._uow() as session:
            views = ViewRepository(session)
            if paging is None or ended:
                found = await views.all()
            else:
                found = await views.live(cutoff)
                hidden = await views.count_ended(cutoff)
        ranked = ordered(found, now)
        if paging is None:
            return [session_json(view, now) for view in ranked]
        return page_json(ranked, now, paging, ended=ended, state=state, ended_hidden=hidden)

    async def _live(self, now: float) -> list[SessionView]:
        async with self._uow() as session:
            return await ViewRepository(session).live(_cutoff(now))

    async def board_views(self, now: float | None = None) -> list[SessionView]:
        """The live sessions, in the order that draws attention."""
        at = self._now() if now is None else now
        return [view for view in ordered(await self._live(at), at) if view.state != "ended"]

    async def subagents_at_work(
        self, now: float | None = None, *, fresh_only: bool = False
    ) -> list[AtWork]:
        """The running subagents of live sessions that work on a ticket."""
        at = self._now() if now is None else now
        found = subagents_at_work(await self.board_views(at))
        return [item for item in found if item.fresh(at)] if fresh_only else found

    async def timeline(self, session_id: str, last: int = DEFAULT_LAST) -> JsonAnswer:
        """One session and its timeline's latest `last` entries.

        Raises:
            NotFoundError: no session has this id.
        """
        now = self._now()
        async with self._uow() as session:
            stored = await ViewRepository(session).get(session_id)
            if stored is None:
                raise NotFoundError("no such session")
            events = await LedgerRepository(session).events_from(session_id)
        entries = rules_timeline.timeline(events)
        shown, earlier = rules_timeline.window(entries, last)
        return {
            "session": session_json(settled(stored.view, now), now),
            "entries": [rules_timeline.entry_json(entry) for entry in shown],
            "total": len(entries),
            "earlier_prompts": earlier,
        }

    async def call(self, session_id: str, seq: int) -> JsonAnswer:
        """The input and output of one tool call.

        Raises:
            NotFoundError: the session has no tool call with this `seq`.
        """
        async with self._uow() as session:
            events = await LedgerRepository(session).events_from(session_id, seq)
        found = rules_timeline.tool_call(events, seq)
        if found is None:
            raise NotFoundError(f"no call {seq} in session {session_id}")
        return {"tool": found.tool, "input": found.input, "output": found.output}
