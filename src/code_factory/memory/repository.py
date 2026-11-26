"""Queries over the memory table. Every method runs in the session it is given."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.memory.models import MemoryFilter
from code_factory.memory.tables import MemoryEntryRow
from code_factory.platform.db import lock_until_commit


class MemoryRepository:
    """A repository's memory entries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, values: dict[str, Any]) -> MemoryEntryRow:
        """Insert an entry."""
        row = MemoryEntryRow(**values)
        self._session.add(row)
        await self._session.flush()
        return row

    async def flush(self) -> None:
        """Write the pending changes, so a query in the same unit of work reads them."""
        await self._session.flush()

    async def remove(self, row: MemoryEntryRow) -> None:
        """Delete an entry's row."""
        await self._session.delete(row)
        await self._session.flush()

    async def find(
        self, repository: str, name: str, *, for_update: bool = False
    ) -> MemoryEntryRow | None:
        """The entry `name` of `repository`, locked against concurrent writers when asked."""
        query = select(MemoryEntryRow).where(
            MemoryEntryRow.repository == repository, MemoryEntryRow.name == name
        )
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query)

    async def lock_additions(self, repository: str) -> None:
        """Hold the repository's additions to one writer until the transaction ends."""
        await lock_until_commit(self._session, f"memory:{repository}")

    async def names(self, repository: str) -> set[str]:
        """Every name taken in the repository, retired entries included."""
        rows = await self._session.scalars(
            select(MemoryEntryRow.name).where(MemoryEntryRow.repository == repository)
        )
        return set(rows)

    async def select(self, where: MemoryFilter) -> list[MemoryEntryRow]:
        """The entries of the filter's repository and kinds, oldest first (day, name, repository).

        The status is the caller's to apply: it is read from three columns.
        """
        query = select(MemoryEntryRow)
        if where.repository is not None:
            query = query.where(MemoryEntryRow.repository == where.repository)
        if where.kinds is not None:
            query = query.where(MemoryEntryRow.kind.in_(where.kinds))
        query = query.order_by(
            MemoryEntryRow.written_on, MemoryEntryRow.name, MemoryEntryRow.repository
        )
        return list(await self._session.scalars(query))

    async def count_proposed_by(self, subject: str) -> int:
        """How many entries `subject` proposed."""
        count = await self._session.scalar(
            select(func.count())
            .select_from(MemoryEntryRow)
            .where(MemoryEntryRow.proposed_by == subject)
        )
        return count or 0
