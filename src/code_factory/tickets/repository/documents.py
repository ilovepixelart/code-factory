"""Queries over a ticket's documents and mock images."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.tickets.models import MockFileInfo
from code_factory.tickets.tables import TicketDocumentRow, TicketMockFileRow


class DocumentRepository:
    """A ticket's documents."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, number: int, name: str) -> TicketDocumentRow | None:
        """The ticket's document `name`."""
        return await self._session.get(TicketDocumentRow, (number, name))

    async def of(self, number: int) -> list[TicketDocumentRow]:
        """Every document of the ticket."""
        rows = await self._session.scalars(
            select(TicketDocumentRow).where(TicketDocumentRow.ticket_number == number)
        )
        return list(rows)

    async def save(self, row: TicketDocumentRow) -> None:
        """Insert or update the document."""
        self._session.add(row)
        await self._session.flush()

    async def remove(self, row: TicketDocumentRow) -> None:
        """Delete the document."""
        await self._session.delete(row)
        await self._session.flush()


class MockFileRepository:
    """A ticket's mock images."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, number: int, name: str) -> TicketMockFileRow | None:
        """The ticket's image `name`."""
        return await self._session.get(TicketMockFileRow, (number, name))

    async def infos(self, number: int) -> list[MockFileInfo]:
        """Every image of the ticket by name, without its bytes (their length is read in SQL)."""
        rows = await self._session.execute(
            select(
                TicketMockFileRow.name,
                TicketMockFileRow.content_type,
                func.octet_length(TicketMockFileRow.data),
                TicketMockFileRow.updated_by,
                TicketMockFileRow.updated_at,
            )
            .where(TicketMockFileRow.ticket_number == number)
            .order_by(TicketMockFileRow.name)
        )
        return [
            MockFileInfo(name=name, content_type=kind, size=size, updated_by=by, updated_at=at)
            for name, kind, size, by, at in rows.all()
        ]

    async def save(self, row: TicketMockFileRow) -> None:
        """Insert or update the image."""
        self._session.add(row)
        await self._session.flush()

    async def remove(self, row: TicketMockFileRow) -> None:
        """Delete the image."""
        await self._session.delete(row)
        await self._session.flush()
