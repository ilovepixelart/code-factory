"""The saved views: the board's filters kept under a name."""

from code_factory.board.repository import ViewRepository
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError


class ViewBook:
    """Saved views in the order they were saved."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def all(self) -> list[dict[str, str]]:
        """Each view's name and the address query it applies."""
        async with self._uow() as session:
            return [{"name": v.name, "query": v.query} for v in await ViewRepository(session).all()]

    async def save(self, name: str, query: str) -> None:
        """Keep the board's current filters under a name."""
        kept = name.strip()
        if not kept:
            raise BadRequestError("A view needs a name")
        async with self._uow() as session:
            if not await ViewRepository(session).add(kept, query.strip()):
                raise ConflictError("A view with this name already exists")

    async def delete(self, name: str) -> None:
        """Delete a view; `NotFoundError` when there is none of that name."""
        async with self._uow() as session:
            if not await ViewRepository(session).remove(name.strip()):
                raise NotFoundError("No view with this name")
