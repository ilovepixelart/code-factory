"""The repositories module's public API: which checkouts the board tracks.

A repository is addressed by its folder name. The caller resolves a worktree to its main checkout
(git's job) and passes that root; nothing here touches the filesystem. Each method is one unit of
work.
"""

import builtins
from pathlib import Path

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import ConflictError, NotFoundError
from code_factory.repositories.models import RepositoryRecord
from code_factory.repositories.repository import RepositoryStore
from code_factory.repositories.rules import checked_root, name_of
from code_factory.repositories.tables import RepositoryRow


def _record(row: RepositoryRow) -> RepositoryRecord:
    return RepositoryRecord(name=row.name, path=row.path)


class RepositoryService:
    """Tracked repositories: list, look up a root by name, track and untrack."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def list(self) -> builtins.list[RepositoryRecord]:
        """Every tracked repository, ordered by name."""
        async with self._uow() as session:
            return [_record(row) for row in await RepositoryStore(session).all()]

    async def get(self, name: str) -> Path:
        """The main checkout of the repository called `name`.

        Raises `NotFoundError` ("unknown repository", the sentence the app shows) when none is.
        """
        async with self._uow() as session:
            row = await RepositoryStore(session).find(name)
        if row is None:
            msg = "unknown repository"
            raise NotFoundError(msg)
        return Path(row.path)

    async def track(self, root: Path) -> RepositoryRecord:
        """Track the checkout at `root`; tracking the same root again changes nothing.

        Raises `ConflictError` when another folder of the same name is tracked, and
        `BadRequestError` for a relative root or one with no folder name.
        """
        checked = checked_root(root)
        name, path = name_of(checked), checked.as_posix()
        async with self._uow() as session:
            row = await RepositoryStore(session).add(name, path)
            if row.path != path:  # raised inside the block so the no-op write rolls back
                msg = f"a repository named {name} is tracked already at {row.path}"
                raise ConflictError(msg)
            return _record(row)

    async def untrack(self, root: Path) -> bool:
        """Stop tracking the checkout at `root`; false when it was not tracked."""
        checked = checked_root(root)
        async with self._uow() as session:
            return await RepositoryStore(session).remove(name_of(checked), checked.as_posix())
