"""Queries over the halt row and the previews."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.runs.models import Halt, PreviewRecord
from code_factory.runs.tables import AgentHaltRow, RunPreviewRow


class HaltRepository:
    """The singleton row that says every agent is stopped."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def halt(self, by: str, at: datetime) -> bool:
        """Record the halt; `False` when one is already recorded (its time and actor stay)."""
        added = await self._session.scalar(
            insert(AgentHaltRow)
            .values(id=1, halted_at=at, by=by)
            .on_conflict_do_nothing()
            .returning(AgentHaltRow.id)
        )
        return added is not None

    async def resume(self) -> bool:
        """Delete the halt; `False` when there was none."""
        gone = await self._session.scalar(delete(AgentHaltRow).returning(AgentHaltRow.id))
        return gone is not None

    async def halted(self) -> Halt | None:
        """The halt, or `None` while agents may start."""
        row = await self._session.scalar(select(AgentHaltRow))
        return None if row is None else Halt(halted_at=row.halted_at, by=row.by)


def _record(row: RunPreviewRow) -> PreviewRecord:
    return PreviewRecord.model_validate(row, from_attributes=True)


class PreviewRepository:
    """A ticket's running preview, one by ticket."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def put(self, preview: PreviewRecord) -> None:
        """Record the preview in place of any the ticket had."""
        values = preview.model_dump()
        await self._session.execute(
            insert(RunPreviewRow)
            .values(**values)
            .on_conflict_do_update(index_elements=["ticket_id"], set_=values)
        )

    async def get(self, number: int) -> PreviewRecord | None:
        """The ticket's preview, or `None`."""
        row = await self._session.get(RunPreviewRow, number, populate_existing=True)
        return None if row is None else _record(row)

    async def delete(self, number: int, pgid: int | None = None) -> bool:
        """Remove the ticket's preview, only the one of process group `pgid` when it is given.

        `False` when there is none, or when a later start replaced the one that was checked.
        """
        query = delete(RunPreviewRow).where(RunPreviewRow.ticket_id == number)
        if pgid is not None:
            query = query.where(RunPreviewRow.pgid == pgid)
        gone = await self._session.scalar(query.returning(RunPreviewRow.ticket_id))
        return gone is not None

    async def all(self) -> list[PreviewRecord]:
        """Every recorded preview."""
        rows = (await self._session.scalars(select(RunPreviewRow))).all()
        return [_record(row) for row in rows]
