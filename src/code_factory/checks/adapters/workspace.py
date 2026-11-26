"""The tree a run's checks judge: a snapshot of a pull request's head or a copy of main's tip.

A snapshot is a detached worktree among the board's trees, which no run, session or person writes
but the checks themselves; it gets the ticket's build cache before the setup and gives it back
when the checks passed. A main copy is a repository of its own in a temporary folder: under the
board's trees it would stand for the checkout, whose files a checks container does not hold.
"""

import hashlib
import math
import shlex
import shutil
import tempfile
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import anyio
import anyio.to_thread

from code_factory.checks.adapters import cache
from code_factory.checks.rules import cache_key
from code_factory.git.service import GitService
from code_factory.platform.contained import ContainedRunner, Work
from code_factory.platform.errors import UnavailableError

TEARDOWN_S = 30.0
MAIN_PREFIX = "code-factory-main-"
TREES = ".code-factory/worktrees"  # where `GitService.add_snapshot` makes its trees
_files = anyio.CapacityLimiter(2)


@dataclass(frozen=True)
class Setup:
    """The repository's `[agents] setup` command and its limit."""

    command: str
    limit_s: float


class SetupFailedError(Exception):
    """The setup did not pass; `str(error)` is the sentence the log and the record hold."""


@dataclass
class Workspace:
    """A tree to check and its git folder; `passed` is set when its checks passed.

    The git folder is read before anything runs in the tree: the `.git` file inside it is the
    checks' to rewrite.
    """

    path: Path
    git_dir: Path
    passed: bool = False


def main_prefix(root: Path) -> str:
    """What the folders holding copies of a repository's default branch are named by."""
    return f"{MAIN_PREFIX}{hashlib.sha256(str(root).encode()).hexdigest()[:12]}-"


def _admin_of(tree: Path) -> Path:
    """The git folder of a worktree, as its `.git` file names it."""
    text = (tree / ".git").read_text(encoding="utf-8").strip()
    admin = Path(text.removeprefix("gitdir:").strip())
    if not admin.is_absolute() or admin.parent.name != "worktrees":
        msg = f"{tree} is not a worktree the board made: its .git file names {admin}"
        raise UnavailableError(msg)
    return admin


def _make_scratch(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix)).resolve()


def _remove_left(prefix: str, keep: frozenset[str], cutoff: float) -> list[str]:
    removed = []
    for entry in sorted(Path(tempfile.gettempdir()).iterdir()):
        if not entry.name.startswith(prefix) or str(entry.resolve()) in keep:
            continue
        if entry.is_symlink() or not entry.is_dir() or entry.stat().st_mtime >= cutoff:
            continue
        shutil.rmtree(entry, ignore_errors=True)
        removed.append(str(entry))
    return removed


def _stray_snapshots(folder: Path, keep: frozenset[str], cutoff: float) -> list[Path]:
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return []
    found = []
    for entry in entries:
        try:
            old = entry.lstat().st_mtime < cutoff
        except OSError:
            continue
        real = entry.resolve()
        if entry.name.startswith("check-") and old and str(real) not in keep:
            found.append(entry)
    return found


def _resolved(path: Path) -> str:
    return str(path.resolve())


def _remove_tree(path: Path) -> None:
    if not path.is_symlink() and path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


async def _shielded(work: Awaitable[object]) -> None:
    """Finish `work` even while the caller is being cancelled, for at most `TEARDOWN_S`."""
    with anyio.CancelScope(shield=True), anyio.move_on_after(TEARDOWN_S):
        await work


class Workspaces:
    """Makes and removes the trees checks run in."""

    def __init__(self, git: GitService, runner: ContainedRunner, state_dir: Path) -> None:
        self._git = git
        self._runner = runner
        self._state = state_dir
        self._live: set[str] = set()  # the resolved trees and scratch folders in use here

    async def _in_use(self, path: Path) -> str:
        found = await anyio.to_thread.run_sync(_resolved, path, limiter=_files)
        self._live.add(found)
        return found

    async def _setup(  # the places one setup runs in
        self, repository: str, tree: Path, log: Path, setup: Setup | None, store: Path | None
    ) -> None:
        if setup is None:
            return
        env = ""
        if store is not None:
            quoted = shlex.quote(str(store))
            env = f"pnpm_config_store_dir={quoted}; export pnpm_config_store_dir; "
        code = await self._runner.run(
            Work.SETUP, repository, f"{env}{setup.command}", tree, log, setup.limit_s
        )
        if code != 0:
            how = "did not finish in time" if code is None else f"failed with exit code {code}"
            msg = f"the snapshot's setup {how}; see {log}"
            raise SetupFailedError(msg)

    def _setup_log(self, tree: Path) -> Path:
        """Where a snapshot's setup writes: beside the checks' logs, which prune ages out."""
        return self._state / "checks" / f"{tree.name}.setup.log"

    async def _cache(self, work: Callable[..., None], *args: object) -> None:
        await anyio.to_thread.run_sync(work, *args, limiter=cache.CACHE_LIMITER)

    @asynccontextmanager
    async def snapshot(
        self, repository: str, commit: str, ticket: str, setup: Setup | None
    ) -> AsyncGenerator[Workspace]:
        """A snapshot of `commit` set up as a worktree is, removed when the block ends.

        The block sets `passed` when the checks passed: the build folder then stays the ticket's.
        Raises `SetupFailedError` (after removing the tree) when the setup does not pass.
        """
        key = cache_key(ticket)
        tree = await self._git.add_snapshot(repository, commit)
        place = tree / cache.LINUX_TARGET
        space = Workspace(tree, tree)
        live = await self._in_use(tree)
        try:
            space.git_dir = await anyio.to_thread.run_sync(_admin_of, tree, limiter=_files)
            await self._cache(cache.adopt, self._state, key, "linux-target", tree, place)
            store = tree / cache.PNPM_STORE
            await self._cache(cache.adopt, self._state, key, "pnpm-store", tree, store)
            try:
                await self._setup(repository, tree, self._setup_log(tree), setup, store)
            except SetupFailedError:
                await self._cache(cache.discard, tree, store)
                raise
            await self._cache(cache.keep, self._state, key, "pnpm-store", tree, store)
            yield space
        finally:
            self._live.discard(live)
            await _shielded(self._end_snapshot(repository, key, space, place))

    async def _end_snapshot(self, repository: str, key: str, space: Workspace, place: Path) -> None:
        tree = space.path
        if space.passed:
            await self._cache(cache.keep, self._state, key, "linux-target", tree, place)
        else:
            await self._cache(cache.discard, tree, place)
        await self._git.remove_snapshot(repository, tree)

    @asynccontextmanager
    async def main_copy(
        self, repository: str, root: Path, commit: str, log: Path, setup: Setup | None
    ) -> AsyncGenerator[Workspace]:
        """A copy of `commit` in a temporary folder, set up and removed when the block ends."""
        prefix = main_prefix(root)
        await anyio.to_thread.run_sync(
            _remove_left, prefix, frozenset(self._live), math.inf, limiter=_files
        )
        scratch = await anyio.to_thread.run_sync(_make_scratch, prefix, limiter=_files)
        tree = scratch / "tree"
        live = await self._in_use(scratch)
        try:
            await self._git.copy_commit(repository, commit, tree)
            await self._setup(repository, tree, log, setup, None)
            yield Workspace(tree, tree / ".git")
        finally:
            self._live.discard(live)
            await _shielded(anyio.to_thread.run_sync(_remove_tree, scratch, limiter=_files))

    async def sweep_copies(self, prefix: str, keep: frozenset[str], cutoff: float) -> list[str]:
        """Remove the copies a stopped process left: not in `keep`, last changed before `cutoff`."""
        return await anyio.to_thread.run_sync(
            _remove_left, prefix, keep | self._live, cutoff, limiter=_files
        )

    async def sweep_snapshots(
        self, repository: str, root: Path, keep: frozenset[str], cutoff: float
    ) -> list[str]:
        """Remove `check-*` trees of `repository` that no live run names and that are old.

        `keep` holds the resolved paths live runs name; `cutoff` is a time in seconds.
        """
        found = await anyio.to_thread.run_sync(
            _stray_snapshots, root / TREES, keep | self._live, cutoff, limiter=_files
        )
        for path in found:
            await self._git.remove_snapshot(repository, path)
        return [str(path) for path in found]
