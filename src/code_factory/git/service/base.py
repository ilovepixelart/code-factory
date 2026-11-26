"""What every part of the git service shares: the ports, the runner, tree validation."""

import asyncio
import os
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from code_factory.git.adapters.folders import common_dir_of, snapshot_tree, threaded
from code_factory.git.adapters.runner import GitRunner
from code_factory.git.models import (
    GitFacts,
    Redirected,
    TreeFolders,
    TreeRecord,
    TreeRedirectedError,
)
from code_factory.git.ports import (
    ChecksPort,
    ForgePort,
    HooksPort,
    RepositoryDirectory,
    ScreenPort,
    TicketPort,
)
from code_factory.git.repository import GitStore
from code_factory.git.rules.folders import board_tree_of, validate_tree
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import NotFoundError

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class GitPorts:
    """What the git service reads from other modules."""

    directory: RepositoryDirectory
    tickets: TicketPort
    forge: ForgePort
    checks: ChecksPort
    screen: ScreenPort
    hooks: HooksPort


def _now() -> datetime:
    return datetime.now(UTC)


class GitBase:
    """The state of a `GitService`: unit of work, runner, ports and the facts in flight."""

    def __init__(
        self, uow: UnitOfWork, runner: GitRunner, ports: GitPorts, clock: Clock = _now
    ) -> None:
        self._uow = uow
        self._runner = runner
        self._ports = ports
        self._clock = clock
        self._flights: dict[str, asyncio.Task[GitFacts]] = {}
        self._reading: set[asyncio.Task[GitFacts]] = (
            set()
        )  # strong refs: a read outlives invalidate

    async def _root(self, repository: str) -> Path:
        return await self._ports.directory.root_of(repository)

    async def _record(self, repository: str, name: str) -> TreeRecord | None:
        async with self._uow() as session:
            return await GitStore(session).tree(repository, name)

    async def _folders(self, repository: str, name: str, at: Path | None = None) -> TreeFolders:
        """The validated folders of a recorded tree; raises when it does not validate.

        `at` is a path inside the tree: a `.git` between it and the tree redirects git.
        """
        record = await self._record(repository, name)
        if record is None:
            msg = f"no tree {name} is recorded for {repository}"
            raise NotFoundError(msg)
        root = await self._root(repository)
        snapshot = await threaded(lambda: snapshot_tree(Path(record.path), root, at))
        found = validate_tree(snapshot, record)
        if isinstance(found, Redirected):
            raise TreeRedirectedError(found.reason)
        return found

    async def _guard_path(self, path: Path) -> tuple[Path, bool]:
        """The path with its links resolved, and whether it is in a clone.

        A board tree is found and validated on the resolved path: git then runs guarded however
        the caller reached it. A tree that fails validation raises.
        """
        real = await threaded(lambda: Path(os.path.realpath(path)))
        found = board_tree_of(str(real))
        if found is None:
            return path, False
        checkout, tree = found
        repository = await self._ports.directory.by_path(Path(checkout))
        folders = await self._folders(repository, Path(tree).name, real)
        return real, folders.is_clone

    async def _common(self, repository: str) -> Path:
        root = await self._root(repository)
        common = await threaded(lambda: common_dir_of(root))
        if common is None:
            msg = f"{root} is not a git repository"
            raise NotFoundError(msg)
        return common

    @staticmethod
    def _spawn[T](work: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
        return asyncio.create_task(work)
