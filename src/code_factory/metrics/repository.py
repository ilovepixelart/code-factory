"""Queries over the metrics tables. Every method runs in the session it is given."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.metrics.models import Autonomy, ChecksVerdict, MergeFact
from code_factory.metrics.tables import BranchCutRow, MergeRow


def _fact(row: MergeRow) -> MergeFact:
    return MergeFact(
        repository=row.repository,
        commit=row.commit,
        head=row.head,
        pull=row.pull,
        branch=row.branch,
        ticket=row.ticket_id,
        at=row.merged_at.timestamp(),
        started=row.started_at.timestamp(),
        reverted=row.reverted,
        autonomy=Autonomy(row.autonomy),
        checks=ChecksVerdict(row.checks),
    )


def _instant(seconds: float) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


class MetricsRepository:
    """The merge ledger and the branch cuts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def merges_since(
        self, since: float, repositories: Sequence[str] | None = None
    ) -> list[MergeFact]:
        """Ledger rows merged at or after `since`, of the named repositories or of all of them."""
        query = select(MergeRow).where(MergeRow.merged_at >= _instant(since))
        if repositories is not None:
            query = query.where(MergeRow.repository.in_(repositories))
        rows = await self._session.scalars(
            query.order_by(MergeRow.merged_at.desc(), MergeRow.commit)
        )
        return [_fact(row) for row in rows]

    async def first_merged(self, tickets: Sequence[str]) -> dict[str, datetime]:
        """When each ticket's first merge that was not reverted landed; one with none is absent."""
        rows = await self._session.execute(
            select(MergeRow.ticket_id, func.min(MergeRow.merged_at))
            .where(MergeRow.ticket_id.in_(tickets), MergeRow.reverted.is_(False))
            .group_by(MergeRow.ticket_id)
        )
        return {ticket: at for ticket, at in rows if ticket is not None}

    async def upsert_merges(self, rows: Sequence[MergeFact], refreshed_at: float) -> None:
        """Insert each row or rewrite the one with its (repository, commit)."""
        if not rows:
            return
        values = [
            {
                "repository": row.repository,
                "commit": row.commit,
                "head": row.head,
                "pull": row.pull,
                "branch": row.branch,
                "ticket_id": row.ticket,
                "merged_at": _instant(row.at),
                "started_at": _instant(row.started),
                "reverted": row.reverted,
                "autonomy": row.autonomy.value,
                "checks": row.checks.value,
                "refreshed_at": _instant(refreshed_at),
            }
            for row in rows
        ]
        statement = insert(MergeRow).values(values)
        changed = {
            name: statement.excluded[name]
            for name in values[0]
            if name not in {"repository", "commit"}
        }
        await self._session.execute(
            statement.on_conflict_do_update(index_elements=["repository", "commit"], set_=changed)
        )

    async def delete_merges(self, repository: str, commits: Sequence[str]) -> None:
        """Remove the rows of these commits of `repository`."""
        if commits:
            await self._session.execute(
                delete(MergeRow).where(
                    MergeRow.repository == repository, MergeRow.commit.in_(commits)
                )
            )

    async def cuts(self, repository: str) -> dict[str, float | None]:
        """When each recorded branch of `repository` was cut; None where git could not tell."""
        rows = await self._session.scalars(
            select(BranchCutRow).where(BranchCutRow.repository == repository)
        )
        return {row.branch: row.cut_at.timestamp() if row.cut_at else None for row in rows}

    async def upsert_cuts(
        self, repository: str, cuts: dict[str, float | None], refreshed_at: float
    ) -> None:
        """Insert each branch's cut or rewrite the one it has."""
        if not cuts:
            return
        values = [
            {
                "repository": repository,
                "branch": branch,
                "cut_at": None if cut is None else _instant(cut),
                "refreshed_at": _instant(refreshed_at),
            }
            for branch, cut in cuts.items()
        ]
        statement = insert(BranchCutRow).values(values)
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["repository", "branch"],
                set_={
                    "cut_at": statement.excluded.cut_at,
                    "refreshed_at": statement.excluded.refreshed_at,
                },
            )
        )

    async def delete_cuts_except(self, repository: str, keep: Sequence[str]) -> None:
        """Remove the cuts of `repository` whose branch is not in `keep`."""
        await self._session.execute(
            delete(BranchCutRow).where(
                BranchCutRow.repository == repository, BranchCutRow.branch.not_in(keep)
            )
        )
