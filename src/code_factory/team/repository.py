"""Queries over the team tables. Every method runs in the session it is given.

Times are epoch seconds outside and `timestamptz` inside: `to_moment` and `to_seconds` are the one
converter pair.
"""

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.db import lock_until_commit
from code_factory.platform.errors import ConflictError, NotFoundError
from code_factory.team.models import Lease
from code_factory.team.rules import claim_ticket
from code_factory.team.tables import TeamLeaseRow, TeamLeaseRunRow

# Serialises claim and pick across processes: two claims never read the same free agent.
LOCK_KEY = "team"
_FOREIGN_KEY_VIOLATION = "23503"
_UNIQUE_VIOLATION = "23505"


def to_moment(seconds: float) -> datetime:
    """An epoch second as a UTC time."""
    return datetime.fromtimestamp(seconds, UTC)


def to_seconds(moment: datetime) -> float:
    """A time as epoch seconds."""
    return moment.timestamp()


class LeaseRepository:
    """Claims and the runs recorded under them."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self) -> None:
        """Take the module's advisory lock until the transaction ends."""
        await lock_until_commit(self._session, LOCK_KEY)

    async def all(self, numbers: Iterable[int] | None = None) -> dict[str, Lease]:
        """The claims of these tickets (every claim without `numbers`) by ticket id.

        Each carries the run ids under it, in order.
        """
        query = select(TeamLeaseRow)
        runs_query = select(TeamLeaseRunRow.lease_id, TeamLeaseRunRow.run_id)
        if numbers is not None:
            wanted = list(numbers)
            query = query.where(TeamLeaseRow.ticket_number.in_(wanted))
            runs_query = runs_query.join(
                TeamLeaseRow, TeamLeaseRow.id == TeamLeaseRunRow.lease_id
            ).where(TeamLeaseRow.ticket_number.in_(wanted))
        rows = (await self._session.execute(query)).scalars().all()
        run_ids: dict[int, list[str]] = {}
        runs = await self._session.execute(
            runs_query.order_by(TeamLeaseRunRow.lease_id, TeamLeaseRunRow.run_id)
        )
        for lease_id, run_id in runs:
            run_ids.setdefault(lease_id, []).append(run_id)
        return {
            claim_ticket(row.ticket_number): Lease(
                agent=row.agent,
                runs=tuple(run_ids.get(row.id, ())),
                claimed_at=to_seconds(row.claimed_at),
                beat_at=to_seconds(row.beat_at),
            )
            for row in rows
        }

    async def add(self, number: int, agent: str, now: float) -> None:
        """Insert the ticket's claim.

        `ConflictError` when it has one (the unique ticket is the guard against a double claim),
        `NotFoundError` when the ticket does not exist.
        """
        try:
            async with self._session.begin_nested():
                self._session.add(
                    TeamLeaseRow(
                        ticket_number=number,
                        agent=agent,
                        claimed_at=to_moment(now),
                        beat_at=to_moment(now),
                    )
                )
                await self._session.flush()
        except IntegrityError as error:
            code = getattr(error.orig, "sqlstate", "")
            if code == _UNIQUE_VIOLATION:
                msg = f"{claim_ticket(number)} already has a claim"
                raise ConflictError(msg) from error
            if code == _FOREIGN_KEY_VIOLATION:
                msg = f"{claim_ticket(number)} does not exist; list the tickets to find its id"
                raise NotFoundError(msg) from error
            raise

    async def replace(self, number: int, agent: str, now: float) -> None:
        """Give the ticket a fresh claim for `agent` in place of any claim it has."""
        await self.delete(number)
        await self.add(number, agent, now)

    async def attach(self, number: int, run_id: str) -> bool:
        """Record a run under the ticket's claim; `False` when the ticket has no claim."""
        lease_id = await self._session.scalar(
            select(TeamLeaseRow.id).where(TeamLeaseRow.ticket_number == number)
        )
        if lease_id is None:
            return False
        await self._session.execute(
            pg_insert(TeamLeaseRunRow)
            .values(lease_id=lease_id, run_id=run_id)
            .on_conflict_do_nothing()
        )
        return True

    async def delete(self, number: int) -> bool:
        """Delete the ticket's claim and the runs under it; whether it had one."""
        result = await self._session.execute(
            delete(TeamLeaseRow)
            .where(TeamLeaseRow.ticket_number == number)
            .returning(TeamLeaseRow.id)
        )
        return result.first() is not None

    async def delete_many(self, numbers: Iterable[int]) -> None:
        """Delete the claims of these tickets."""
        await self._session.execute(
            delete(TeamLeaseRow).where(TeamLeaseRow.ticket_number.in_(list(numbers)))
        )

    async def beat(self, numbers: Iterable[int], now: float) -> None:
        """Move the heartbeat of these tickets' claims to `now`."""
        await self._session.execute(
            update(TeamLeaseRow)
            .where(TeamLeaseRow.ticket_number.in_(list(numbers)))
            .values(beat_at=to_moment(now))
        )
