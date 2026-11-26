"""The one place `git` is started: trusted program, reduced environment, limits, concurrency.

Commands run through `platform.process.run_process` (own session, output cap, SIGTERM then SIGKILL
and always reaped). Per repository root at most `READS` run at once, under a process-wide cap;
operations that move refs or add and remove trees of one repository take that repository's ref
lock; reads never wait on it.
"""

import asyncio
import os
from collections import defaultdict
from collections.abc import AsyncGenerator, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, Unpack

from code_factory.git.models import TreeRedirectedError
from code_factory.git.rules.folders import board_tree_of, guarded
from code_factory.platform.errors import UnavailableError
from code_factory.platform.process import MIB, run_process
from code_factory.platform.programs import REPOSITORY_VARIABLES, find_program

READS = 8
PROCESSES = 32
READ_TIMEOUT_S = 60.0
LOG_TIMEOUT_S = 120.0
NETWORK_TIMEOUT_S = 300.0
WRITE_TIMEOUT_S = 600.0
OUTPUT_CAP = 8 * MIB
DIFF_CAP = 4 * MIB
FIXED_ENV = {"GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}


class RunOptions(TypedDict, total=False):
    """The limits and settings of one call."""

    timeout_s: float
    cap: int
    clone: bool
    env: dict[str, str]


@dataclass(frozen=True)
class GitResult:
    """What a git command did; `code` is `None` when a limit stopped it."""

    code: int | None
    stdout: str
    stderr: str
    truncated: bool = False

    @property
    def ok(self) -> bool:
        """Whether it exited 0 within its limits."""
        return self.code == 0


def trusted_path(env: dict[str, str]) -> str:
    """`PATH` reduced to absolute folders."""
    return os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if p.startswith("/"))


def child_env(base: dict[str, str], *, clone_git_dir: str | None = None) -> dict[str, str]:
    """The environment of a git child: repository variables removed, fixed settings added."""
    env = {k: v for k, v in base.items() if k not in REPOSITORY_VARIABLES}
    env["PATH"] = trusted_path(base)
    env.update(FIXED_ENV)
    if clone_git_dir is not None:
        env["GIT_COMMON_DIR"] = clone_git_dir
    return env


class GitRunner:
    """Runs git. `places` are the folders a run may write; a program found there is not trusted."""

    def __init__(self, places: Sequence[Path] = (), *, program: Path | None = None) -> None:
        self._places = tuple(places)
        self._program = program
        self._reads: defaultdict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(READS)
        )
        self._ref_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._tree_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._process_cap = asyncio.Semaphore(PROCESSES)
        self.calls = 0

    async def program(self) -> Path:
        """The git to start, resolved once to a file only root or the user can write."""
        if self._program is None:
            found = await find_program("git", self._places)
            if found is None:
                msg = "git is not installed in a folder only you can write; install it and retry"
                raise UnavailableError(msg)
            self._program = found
        return self._program

    @asynccontextmanager
    async def ref_lock(self, root: Path) -> AsyncGenerator[None]:
        """Serialise operations that move refs or add and remove trees of one repository."""
        async with self._ref_locks[str(root)]:
            yield

    @asynccontextmanager
    async def tree_lock(self, tree: Path) -> AsyncGenerator[None]:
        """Serialise writes in one tree."""
        async with self._tree_locks[str(tree)]:
            yield

    async def run(  # noqa: PLR0913  # one call with its limits
        self,
        root: Path,
        args: Sequence[str],
        *,
        timeout_s: float = READ_TIMEOUT_S,
        cap: int = OUTPUT_CAP,
        clone: bool = False,
        env: dict[str, str] | None = None,
    ) -> GitResult:
        """`git --no-optional-locks -C root <args>`; guarded when `root` is in a board tree.

        `clone` sets `GIT_COMMON_DIR` to the clone's own `.git`, which git reads before any
        `commondir` file a run could have planted.
        """
        program = await self.program()
        in_tree = board_tree_of(str(root)) is not None
        words = [
            str(program),
            "--no-optional-locks",
            "-C",
            str(root),
            *guarded(list(args), in_tree=in_tree),
        ]
        child = child_env(dict(os.environ), clone_git_dir=f"{root}/.git" if clone else None)
        child.update(env or {})
        async with self._reads[str(root)], self._process_cap:
            self.calls += 1
            done = await run_process(words, env=child, timeout_s=timeout_s, output_cap=cap)
        if done.timed_out:
            command = args[0] if args else ""
            msg = f"git {command} in {root} took more than {timeout_s:g} s and was stopped"
            raise UnavailableError(msg)
        return GitResult(
            done.code,
            done.stdout.decode(errors="replace"),
            done.stderr.decode(errors="replace"),
            truncated=done.truncated,
        )

    async def ok(self, root: Path, args: Sequence[str], **kw: Unpack[RunOptions]) -> str | None:
        """Stdout, stripped, when git exits 0; `None` when it fails."""
        done = await self.run(root, args, **kw)
        return done.stdout.strip() if done.ok else None

    async def checked(self, root: Path, args: Sequence[str], **kw: Unpack[RunOptions]) -> str:
        """Stdout, stripped; raises `UnavailableError` with git's words when it fails."""
        done = await self.run(root, args, **kw)
        if not done.ok:
            why = (done.stderr.strip() or done.stdout.strip()).splitlines()
            msg = f"git {args[0] if args else ''} failed: {why[-1] if why else 'no output'}"
            raise UnavailableError(msg)
        return done.stdout.strip()


async def acquire_all(stack: AsyncExitStack, *locks: asyncio.Lock) -> None:
    """Take several locks in the order given."""
    for lock in locks:
        await stack.enter_async_context(lock)


__all__ = ["GitResult", "GitRunner", "TreeRedirectedError", "child_env"]
