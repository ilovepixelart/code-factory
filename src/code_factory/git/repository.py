"""Queries over the git tables. Every method runs in the session it is given."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.git.models import MergeCheck, TreeKind, TreeRecord
from code_factory.git.tables import GitMergeCheckRow, GitTreeRow


def _record(row: GitTreeRow) -> TreeRecord:
    return TreeRecord(
        repository=row.repository,
        name=row.name,
        kind=TreeKind(row.kind),
        ticket_id=row.ticket_id,
        attempt=row.attempt,
        branch=row.branch,
        path=row.path,
        token=row.token,
    )


class GitStore:
    """Tree records and merge checks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_tree(self, record: TreeRecord) -> bool:
        """Insert a record; `False` when the repository already has a tree of that name."""
        statement = (
            insert(GitTreeRow)
            .values(**record.model_dump(mode="json"))
            .on_conflict_do_nothing(index_elements=["repository", "name"])
            .returning(GitTreeRow.id)
        )
        return await self._session.scalar(statement) is not None

    async def tree(self, repository: str, name: str) -> TreeRecord | None:
        """The record of one tree."""
        row = await self._session.scalar(
            select(GitTreeRow).where(GitTreeRow.repository == repository, GitTreeRow.name == name)
        )
        return None if row is None else _record(row)

    async def trees(self, repository: str) -> list[TreeRecord]:
        """Every record of a repository, ordered by name."""
        rows = await self._session.scalars(
            select(GitTreeRow).where(GitTreeRow.repository == repository).order_by(GitTreeRow.name)
        )
        return [_record(row) for row in rows]

    async def remove_tree(self, repository: str, name: str) -> None:
        """Delete a record."""
        await self._session.execute(
            delete(GitTreeRow).where(GitTreeRow.repository == repository, GitTreeRow.name == name)
        )

    async def merge_check(self, repository: str, tip_a: str, tip_b: str) -> MergeCheck | None:
        """The stored answer for an ordered pair."""
        row = await self._session.get(GitMergeCheckRow, (repository, tip_a, tip_b))
        return None if row is None else MergeCheck(clean=row.clean, files=list(row.files))

    async def store_merge_check(
        self, repository: str, pair: tuple[str, str], check: MergeCheck, at: datetime
    ) -> None:
        """Record an answer; asking twice keeps the first."""
        statement = (
            insert(GitMergeCheckRow)
            .values(
                repository=repository, tip_a=pair[0], tip_b=pair[1], clean=check.clean,
                files=check.files, checked_at=at,
            )
            .on_conflict_do_nothing()
        )  # fmt: skip
        await self._session.execute(statement)

    async def forget_merge_checks(self, older_than: datetime) -> int:
        """Delete answers checked before `older_than`; how many."""
        done = await self._session.execute(
            delete(GitMergeCheckRow).where(GitMergeCheckRow.checked_at < older_than)
        )
        return int(getattr(done, "rowcount", 0) or 0)
