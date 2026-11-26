"""Queries over the repositories table. Every method runs in the session it is given."""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.repositories.tables import RepositoryRow


class RepositoryStore:
    """The tracked repositories."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, name: str, path: str) -> RepositoryRow:
        """The repository called `name`, inserted when absent.

        One statement: a row that a concurrent untrack deletes meanwhile is inserted again
        instead of read back missing. The no-op update is what makes `RETURNING` answer the
        existing row.
        """
        result = await self._session.execute(
            insert(RepositoryRow)
            .values(name=name, path=path)
            .on_conflict_do_update(index_elements=["name"], set_={"name": name})
            .returning(RepositoryRow)
        )
        return result.scalar_one()

    async def find(self, name: str) -> RepositoryRow | None:
        """The repository called `name`."""
        return await self._session.scalar(select(RepositoryRow).where(RepositoryRow.name == name))

    async def all(self) -> list[RepositoryRow]:
        """Every repository, ordered by name."""
        rows = await self._session.scalars(select(RepositoryRow).order_by(RepositoryRow.name))
        return list(rows)

    async def remove(self, name: str, path: str) -> bool:
        """Delete the repository when `name` is tracked at `path`; whether a row went."""
        result = await self._session.execute(
            delete(RepositoryRow)
            .where(RepositoryRow.name == name, RepositoryRow.path == path)
            .returning(RepositoryRow.id)
        )
        return result.first() is not None
