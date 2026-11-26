"""Queries over the stored session views."""

import asyncio
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.sessions.models import SessionState, SessionView
from code_factory.sessions.repository.ledger import to_datetime
from code_factory.sessions.tables import SessionEventRow, SessionViewRow

logger = logging.getLogger(__name__)
YIELD_EVERY = 250


@dataclass(frozen=True, slots=True)
class StoredView:
    """A stored row: the unsettled view and what the ingest needs to continue from it."""

    view: SessionView
    last_seq: int
    window_seq: int
    rules_version: int


@dataclass(frozen=True, slots=True)
class NewView:
    """What the ingest writes for a session."""

    view: SessionView
    last_seq: int
    window_seq: int
    rules_version: int


def _stored(row: SessionViewRow) -> StoredView | None:
    """The row as a view; None for one the current code cannot read (the rebuild rewrites it)."""
    try:
        view = SessionView.model_validate(
            {**row.view, "repository": row.repository, "branch": row.branch}
        )
    except ValidationError:
        logger.warning(
            "the stored view of session %r is unreadable; rebuild the views", row.session_id
        )
        return None
    return StoredView(view, row.last_seq, row.window_seq, row.rules_version)


async def _readable(rows: Iterable[SessionViewRow]) -> list[StoredView]:
    """The rows as views, giving the loop a turn every few hundred: a page may hold thousands."""
    found = []
    for count, row in enumerate(rows, 1):
        if (stored := _stored(row)) is not None:
            found.append(stored)
        if count % YIELD_EVERY == 0:
            await asyncio.sleep(0)
    return found


def _live(cutoff: datetime) -> object:
    """Not ended by the clock: blocked, or working or idle with an event after `cutoff`."""
    return or_(
        SessionViewRow.state == SessionState.BLOCKED,
        and_(
            SessionViewRow.state.in_((SessionState.WORKING, SessionState.IDLE)),
            SessionViewRow.last_event_at > cutoff,
        ),
    )


class ViewRepository:
    """The `session_views` table. Every method runs in the session it is given."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, session_id: str) -> StoredView | None:
        """The stored view of one session."""
        row = await self._session.get(SessionViewRow, session_id)
        return None if row is None else _stored(row)

    async def get_many(self, session_ids: Sequence[str]) -> dict[str, StoredView]:
        """The stored views of the named sessions that have one."""
        rows = await self._session.scalars(
            select(SessionViewRow).where(SessionViewRow.session_id.in_(session_ids))
        )
        return {found.view.session_id: found for found in await _readable(rows)}

    async def all(self) -> list[SessionView]:
        """Every stored view."""
        rows = await self._session.scalars(select(SessionViewRow))
        return [found.view for found in await _readable(rows)]

    async def live(self, cutoff: datetime) -> list[SessionView]:
        """The views not ended by the clock as of `cutoff` (an hour before now)."""
        rows = await self._session.scalars(select(SessionViewRow).where(_live(cutoff)))  # ty: ignore[invalid-argument-type]  # a SQL expression
        return [found.view for found in await _readable(rows)]

    async def count_ended(self, cutoff: datetime) -> int:
        """How many sessions `live` leaves out."""
        found = await self._session.scalar(
            select(func.count()).select_from(SessionViewRow).where(~_live(cutoff))  # ty: ignore[unsupported-operator]  # a SQL expression
        )
        return found or 0

    async def transcripts(self, session_ids: Sequence[str] | None) -> dict[str, str]:
        """The transcript of each named session (all when None); unknown ones are left out."""
        query = select(SessionViewRow.session_id, SessionViewRow.transcript)
        if session_ids is not None:
            query = query.where(SessionViewRow.session_id.in_(session_ids))
        return dict((await self._session.execute(query)).all())

    async def upsert(self, views: Sequence[NewView]) -> None:
        """Write the views, replacing a session's earlier row."""
        for item in views:
            view = item.view
            values = {
                "session_id": view.session_id,
                "state": view.state.value,
                "last_event_at": to_datetime(view.last_event_at),
                "last_seq": item.last_seq,
                "window_seq": item.window_seq,
                "cwd": view.cwd,
                "repository": view.repository,
                "branch": view.branch,
                "transcript": view.transcript,
                "rules_version": item.rules_version,
                "view": view.model_dump(mode="json", exclude={"repository", "branch"}),
            }
            statement = insert(SessionViewRow).values(values)
            await self._session.execute(
                statement.on_conflict_do_update(
                    index_elements=["session_id"],
                    set_={
                        **{k: v for k, v in values.items() if k != "session_id"},
                        "updated_at": func.now(),
                    },
                )
            )

    async def stale_session_ids(self, rules_version: int) -> list[str]:
        """The sessions with events and no view, or a view written by older rules."""
        found = await self._session.scalars(
            select(SessionEventRow.session_id)
            .distinct()
            .outerjoin(SessionViewRow, SessionViewRow.session_id == SessionEventRow.session_id)
            .where(
                or_(
                    SessionViewRow.session_id.is_(None),
                    SessionViewRow.rules_version != rules_version,
                )
            )
        )
        return sorted(found)

    async def session_ids(self) -> list[str]:
        """Every session that has events."""
        return sorted(await self._session.scalars(select(SessionEventRow.session_id).distinct()))

    async def delete_orphans(self) -> int:
        """Delete the views of sessions that have no event left; how many."""
        gone = await self._session.scalars(
            delete(SessionViewRow)
            .where(~exists().where(SessionEventRow.session_id == SessionViewRow.session_id))
            .returning(SessionViewRow.session_id)
        )
        return len(gone.all())

    async def clear_rules_version(self) -> None:
        """Mark every stored view as written by no known rules, so the next check rebuilds it."""
        await self._session.execute(update(SessionViewRow).values(rules_version=0))
