"""Queries over `undo_entries`. Every method runs in the session it is given."""

from datetime import datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.undo.tables import UndoEntryRow


class UndoRepository:
    """The stored undos."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(
        self, token: str, kind: str, payload: dict[str, Any], created: datetime, expires: datetime
    ) -> None:
        """Store one entry."""
        self._session.add(
            UndoEntryRow(
                token=token, kind=kind, payload=payload, created_at=created, expires_at=expires
            )
        )
        await self._session.flush()

    async def claim(self, token: str) -> UndoEntryRow | None:
        """Delete and return the entry; of two callers with one token, one gets it."""
        return await self._session.scalar(
            delete(UndoEntryRow).where(UndoEntryRow.token == token).returning(UndoEntryRow)
        )

    async def sweep(self, cutoff: datetime) -> int:
        """Delete the entries that expired before `cutoff`; how many went."""
        deleted = await self._session.scalars(
            delete(UndoEntryRow)
            .where(UndoEntryRow.expires_at < cutoff)
            .returning(UndoEntryRow.token)
        )
        return len(deleted.all())
