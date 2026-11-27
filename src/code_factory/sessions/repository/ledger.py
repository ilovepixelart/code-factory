"""Queries over the event ledger: events, rejects and where the ingest stopped in each spool."""

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Float, Text, delete, func, select, text, update
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.sessions.models import Event, NewEvent, Reject
from code_factory.sessions.tables import (
    SessionEventRow,
    SessionRejectRow,
    SessionSpoolProgressRow,
)

# One key serialises every ingester of a schema: the stream reads by `seq`, so two commits
# interleaving could make a lower `seq` visible after a higher one. The key comes from the schema
# in SQL, so schemas that share a database (the test workers) never wait for each other.
LOCK_KEY = "hashtextextended(current_schema() || '/code-factory-sessions-ingest', 0)"
CHANNEL = "session_events"
LOCK_NOT_AVAILABLE = "55P03"
# asyncpg takes at most 32,767 parameters in one statement.
INSERT_ROWS = 1000

_EPOCH = sql_cast(func.extract("epoch", SessionEventRow.captured_at), Float)
_COLUMNS = (
    SessionEventRow.seq,
    SessionEventRow.session_id,
    SessionEventRow.agent_id,
    SessionEventRow.event,
    _EPOCH,
    SessionEventRow.spool,
    SessionEventRow.spool_offset,
    SessionEventRow.payload,
)


def channel_for(schema: str) -> str:
    """The `NOTIFY` channel of a schema: the plain name for `public`, a short digest otherwise.

    A notification reaches every listener of the database, so schemas keep their own.
    """
    if schema == "public":
        return CHANNEL
    digest = hashlib.sha1(schema.encode(), usedforsecurity=False).hexdigest()[:12]
    return f"{CHANNEL}_{digest}"


def to_datetime(seconds: float) -> datetime:
    """A moment from seconds since the epoch."""
    return datetime.fromtimestamp(seconds, UTC)


def _event(row: Sequence[object]) -> Event:
    seq, session_id, agent_id, name, at, spool, offset, payload = row
    return Event(
        cast("int", seq),
        cast("str", session_id),
        cast("str | None", agent_id),
        cast("str", name),
        cast("float", at),
        cast("str", spool),
        cast("int", offset),
        cast("dict[str, object]", payload),
    )


class LedgerRepository:
    """The ledger tables. Every method runs in the session it is given."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self, *, wait_ms: int | None) -> bool:
        """Take the ingest lock until the transaction ends.

        Waits up to `wait_ms`, or does not wait at all when it is None; whether it was taken.
        """
        if wait_ms is None:
            taken = await self._session.scalar(
                text(f"select pg_try_advisory_xact_lock({LOCK_KEY})")
            )
            return bool(taken)
        await self._session.execute(text(f"set local lock_timeout = {int(wait_ms)}"))
        try:
            async with self._session.begin_nested():
                await self._session.execute(text(f"select pg_advisory_xact_lock({LOCK_KEY})"))
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE:
                return False
            raise
        return True

    async def progress(self) -> dict[str, int]:
        """The byte offset reached in each spool."""
        rows = await self._session.execute(
            select(SessionSpoolProgressRow.spool, SessionSpoolProgressRow.byte_offset)
        )
        return dict(rows.all())

    async def advance(self, spool: str, *, old: int, new: int) -> bool:
        """Move the spool's progress from `old` to `new`; False when another ingester moved it."""
        if old == 0:
            inserted = await self._session.scalar(
                insert(SessionSpoolProgressRow)
                .values(spool=spool, byte_offset=new)
                .on_conflict_do_nothing(index_elements=["spool"])
                .returning(SessionSpoolProgressRow.spool)
            )
            if inserted is not None:
                return True
        moved = await self._session.scalar(
            update(SessionSpoolProgressRow)
            .where(
                SessionSpoolProgressRow.spool == spool, SessionSpoolProgressRow.byte_offset == old
            )
            .values(byte_offset=new, updated_at=func.now())
            .returning(SessionSpoolProgressRow.spool)
        )
        return moved is not None

    async def insert_events(self, rows: Sequence[NewEvent]) -> list[Event]:
        """Insert the events in order; the stored ones, with their `seq`.

        A line already in the ledger (same spool and offset) is left alone and not returned.
        """
        stored: list[Event] = []
        for start in range(0, len(rows), INSERT_ROWS):
            chunk = rows[start : start + INSERT_ROWS]
            by_place = {(row.spool, row.offset): row for row in chunk}
            result = await self._session.execute(
                insert(SessionEventRow)
                .values(
                    [
                        {
                            "session_id": row.session_id,
                            "agent_id": row.agent_id,
                            "event": row.event,
                            "captured_at": to_datetime(row.captured_at),
                            "spool": row.spool,
                            "spool_offset": row.offset,
                            "payload": row.payload,
                        }
                        for row in chunk
                    ]
                )
                .on_conflict_do_nothing(index_elements=["spool", "spool_offset"])
                .returning(SessionEventRow.seq, SessionEventRow.spool, SessionEventRow.spool_offset)
            )
            for seq, spool, offset in sorted(result.all()):
                row = by_place[spool, offset]
                stored.append(
                    Event(
                        seq,
                        row.session_id,
                        row.agent_id,
                        row.event,
                        row.captured_at,
                        spool,
                        offset,
                        row.payload,
                    )
                )
        return stored

    async def insert_rejects(self, rows: Sequence[Reject]) -> None:
        """Keep the lines that are no event; one already kept is left alone."""
        for start in range(0, len(rows), INSERT_ROWS):
            await self._session.execute(
                insert(SessionRejectRow)
                .values(
                    [
                        {
                            "spool": row.spool,
                            "spool_offset": row.offset,
                            "reason": row.reason,
                            "head": row.head,
                        }
                        for row in rows[start : start + INSERT_ROWS]
                    ]
                )
                .on_conflict_do_nothing(index_elements=["spool", "spool_offset"])
            )

    async def notify(self, channel: str, newest: int) -> None:
        """Wake the listeners when this transaction commits; the payload is the newest `seq`."""
        await self._session.execute(
            text("select pg_notify(:channel, :payload)"),
            {"channel": channel, "payload": str(newest)},
        )

    async def events_from(
        self, session_id: str, seq: int = 0, *, upto: int | None = None
    ) -> list[Event]:
        """The events of a session from `seq` (to `upto`) with their payloads, oldest first."""
        query = select(*_COLUMNS).where(
            SessionEventRow.session_id == session_id, SessionEventRow.seq >= seq
        )
        if upto is not None:
            query = query.where(SessionEventRow.seq <= upto)
        rows = await self._session.execute(query.order_by(SessionEventRow.seq))
        return [_event(row) for row in rows]

    async def events_after(self, after: int, limit: int) -> list[Event]:
        """The first `limit` events past `after`, oldest first."""
        rows = await self._session.execute(
            select(*_COLUMNS)
            .where(SessionEventRow.seq > after)
            .order_by(SessionEventRow.seq)
            .limit(limit)
        )
        return [_event(row) for row in rows]

    async def latest_seqs(self, session_ids: Sequence[str]) -> dict[str, int]:
        """The newest `seq` of each named session that still has events."""
        rows = await self._session.execute(
            select(SessionEventRow.session_id, func.max(SessionEventRow.seq))
            .where(SessionEventRow.session_id.in_(session_ids))
            .group_by(SessionEventRow.session_id)
        )
        return dict(rows.all())

    async def spool_counts(self, spools: Sequence[str]) -> tuple[int, int]:
        """How many events and rejects the named spools hold."""
        events = await self._session.scalar(
            select(func.count()).where(SessionEventRow.spool.in_(spools))
        )
        rejects = await self._session.scalar(
            select(func.count()).where(SessionRejectRow.spool.in_(spools))
        )
        return events or 0, rejects or 0

    async def delete_spools(self, spools: Sequence[str]) -> None:
        """Delete the events and rejects of the named spools (not their progress)."""
        await self._session.execute(
            delete(SessionEventRow).where(SessionEventRow.spool.in_(spools))
        )
        await self._session.execute(
            delete(SessionRejectRow).where(SessionRejectRow.spool.in_(spools))
        )

    async def delete_progress(self, spools: Sequence[str]) -> None:
        """Forget where the ingest stopped in the named spools."""
        await self._session.execute(
            delete(SessionSpoolProgressRow).where(SessionSpoolProgressRow.spool.in_(spools))
        )

    async def output_rows(self, since: datetime) -> list[tuple[str, object, object]]:
        """The session, `tool_response` and `error` of each Bash result since `since`.

        Only those whose payload may hold a gate line, as stored: whole, or in a trimmed output.
        """
        payload = SessionEventRow.payload
        rows = await self._session.execute(
            select(SessionEventRow.session_id, payload["tool_response"], payload["error"])
            .where(
                SessionEventRow.event.in_(("PostToolUse", "PostToolUseFailure")),
                SessionEventRow.captured_at >= since,
                payload["tool_name"].astext == "Bash",
                sql_cast(payload, Text).like("%gate: %"),
            )
            .order_by(SessionEventRow.seq)
        )
        return [(session_id, response, error) for session_id, response, error in rows]
