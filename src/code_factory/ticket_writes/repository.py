"""Queries over `column_limits`. Every method runs in the session it is given."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.ticket_writes.tables import ColumnLimitRow


class ColumnLimitRepository:
    """The columns' limits."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self) -> dict[str, int]:
        """Each limited column and its limit."""
        rows = await self._session.execute(select(ColumnLimitRow.stage, ColumnLimitRow.max_open))
        return {stage: limit for stage, limit in rows.all()}  # noqa: C416  # a Row is not a pair

    async def put(self, stage: str, limit: int, now: datetime) -> None:
        """Set the column's limit, replacing the one it had."""
        values = {"max_open": limit, "updated_at": now}
        await self._session.execute(
            insert(ColumnLimitRow)
            .values(stage=stage, **values)
            .on_conflict_do_update(index_elements=["stage"], set_=values)
        )

    async def clear(self, stage: str) -> None:
        """Remove the column's limit; none is no limit."""
        await self._session.execute(delete(ColumnLimitRow).where(ColumnLimitRow.stage == stage))
