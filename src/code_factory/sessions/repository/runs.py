"""Queries over the requests runs reported through their telemetry."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.sessions.models import ReportedTokens, Request
from code_factory.sessions.tables import SessionRunRequestRow

INSERT_ROWS = 1000


class RunRequestRepository:
    """The `session_run_requests` table. Every method runs in the session it is given."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, run_id: str, requests: Sequence[Request]) -> int:
        """Record the requests of a run; how many."""
        for start in range(0, len(requests), INSERT_ROWS):
            await self._session.execute(
                insert(SessionRunRequestRow).values(
                    [
                        {"run_id": run_id, "input_tokens": r.input, "output_tokens": r.output}
                        for r in requests[start : start + INSERT_ROWS]
                    ]
                )
            )
        return len(requests)

    async def totals(self, run_ids: Sequence[str]) -> dict[str, ReportedTokens]:
        """The tokens each named run reported, in one grouped query; runs with no rows are left out.

        The sums are exact (`numeric`) and saturate at the largest `bigint` here.
        """
        rows = await self._session.execute(
            select(
                SessionRunRequestRow.run_id,
                func.sum(SessionRunRequestRow.input_tokens),
                func.sum(SessionRunRequestRow.output_tokens),
            )
            .where(SessionRunRequestRow.run_id.in_(run_ids))
            .group_by(SessionRunRequestRow.run_id)
        )
        biggest = 2**63 - 1
        return {
            run_id: ReportedTokens(min(int(received), biggest), min(int(sent), biggest))
            for run_id, received, sent in rows
        }

    async def forget(self, run_id: str) -> int:
        """Delete a run's requests; how many."""
        gone = await self._session.scalars(
            delete(SessionRunRequestRow)
            .where(SessionRunRequestRow.run_id == run_id)
            .returning(SessionRunRequestRow.id)
        )
        return len(gone.all())

    async def delete_before(self, cutoff: datetime) -> int:
        """Delete the requests reported before `cutoff`; how many."""
        gone = await self._session.scalars(
            delete(SessionRunRequestRow)
            .where(SessionRunRequestRow.reported_at < cutoff)
            .returning(SessionRunRequestRow.id)
        )
        return len(gone.all())

    async def count_before(self, cutoff: datetime) -> int:
        """How many requests were reported before `cutoff`."""
        found = await self._session.scalar(
            select(func.count())
            .select_from(SessionRunRequestRow)
            .where(SessionRunRequestRow.reported_at < cutoff)
        )
        return int(found or 0)
