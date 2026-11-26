"""Queries over `board_views`. Every method runs in the session it is given."""

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.board.tables import BoardViewRow


class ViewRepository:
    """The saved views."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self) -> list[BoardViewRow]:
        """Every view in the order saved."""
        return list(await self._session.scalars(select(BoardViewRow).order_by(BoardViewRow.id)))

    async def add(self, name: str, query: str) -> bool:
        """Store a view; False when the name is taken."""
        try:
            async with self._session.begin_nested():
                self._session.add(BoardViewRow(name=name, query=query))
        except IntegrityError:
            return False
        return True

    async def remove(self, name: str) -> bool:
        """Delete the view; False when there is none of that name."""
        deleted = await self._session.scalars(
            delete(BoardViewRow).where(BoardViewRow.name == name).returning(BoardViewRow.id)
        )
        return deleted.first() is not None
