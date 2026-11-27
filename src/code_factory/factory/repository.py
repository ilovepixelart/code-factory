"""Queries for owner time over one transaction."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from code_factory.factory.models import OwnerTime
from code_factory.factory.tables import OwnerTimeRow
from code_factory.platform.db import AsyncSession


class OwnerTimeRepository:
    """Keep published owner input out of agent-readable ticket history."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, ticket: str, entry: OwnerTime) -> None:
        """Atomically replace the current entry for this ticket and pull."""
        statement = insert(OwnerTimeRow).values(ticket_id=ticket, **entry.model_dump())
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[OwnerTimeRow.ticket_id, OwnerTimeRow.pull_url],
                set_={
                    "active_minutes": statement.excluded.active_minutes,
                    "hourly_rate_usd": statement.excluded.hourly_rate_usd,
                },
            )
        )

    async def recorded(self, tickets: list[str]) -> dict[tuple[str, str], OwnerTime]:
        """Read owner entries for a cohort's tickets."""
        rows = await self._session.scalars(
            select(OwnerTimeRow).where(OwnerTimeRow.ticket_id.in_(tickets))
        )
        return {
            (row.ticket_id, row.pull_url): OwnerTime(
                pull_url=row.pull_url,
                active_minutes=row.active_minutes,
                hourly_rate_usd=row.hourly_rate_usd,
            )
            for row in rows
        }
