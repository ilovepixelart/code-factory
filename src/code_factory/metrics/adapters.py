"""IO at the edge: the one place this module starts `git`.

Every call is `git --no-optional-locks -C <root> ...` through `platform.process.run_process`
(argument list, own session, a time limit, an output cap, SIGTERM then SIGKILL and always reaped),
with the repository variables removed from the environment. A ref follows `--end-of-options` and
the call ends in `--`. At most four calls run at once in the process, and a repository's passes
take its lock. No network, no `gh`, no keychain.
"""

import asyncio
import os
import re
from collections import defaultdict
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from code_factory.metrics.rules.merges import LOG_FORMAT, github_web
from code_factory.metrics.rules.stages import utc_stamp
from code_factory.platform.errors import UnavailableError
from code_factory.platform.process import MIB, ProcessResult, run_process
from code_factory.platform.programs import child_environment, find_program

CONCURRENCY = 4
NO_SUCH_REMOTE = 2  # `git remote get-url` of a remote that is not configured
LOG_TIMEOUT_S = 60.0
READ_TIMEOUT_S = 15.0
ORIGIN_TIMEOUT_S = 10.0
LOG_CAP = 32 * MIB
READ_CAP = 4 * MIB
_FIXED_ENV = {"GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}


class GitUnavailableError(UnavailableError):
    """Git could not answer: the sentence names the repository and what stopped it."""


_REFLOG_TIME = re.compile(r"@\{(\d+)\}")


def _oldest(text: str | None) -> float | None:
    times = [float(line) for line in (text or "").split() if line.isdigit()]
    return min(times) if times else None


def _oldest_entry(reflog: str | None) -> float | None:
    """The time of the oldest reflog entry, from lines like `ticket/cf-1@{1700000000}`."""
    times = [
        float(found[1]) for found in map(_REFLOG_TIME.search, (reflog or "").splitlines()) if found
    ]
    return min(times) if times else None


class GitReader:
    """Reads delivery facts out of a repository's git history."""

    def __init__(  # noqa: PLR0913  # the limits of the reads, all optional
        self,
        program: str = "git",
        *,
        places: Sequence[Path] = (),
        log_timeout_s: float = LOG_TIMEOUT_S,
        read_timeout_s: float = READ_TIMEOUT_S,
        origin_timeout_s: float = ORIGIN_TIMEOUT_S,
        output_cap: int = LOG_CAP,
        concurrency: int = CONCURRENCY,
    ) -> None:
        self._program = program
        self._places = places
        self._log_timeout_s = log_timeout_s
        self._read_timeout_s = read_timeout_s
        self._origin_timeout_s = origin_timeout_s
        self._output_cap = output_cap
        self._calls = asyncio.Semaphore(concurrency)
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    @asynccontextmanager
    async def exclusive(self, root: Path) -> AsyncGenerator[None]:
        """Hold the repository's lock, so two passes over it never overlap."""
        async with self._locks[str(root)]:
            yield

    async def _run(
        self, root: Path, args: Sequence[str], *, timeout_s: float, cap: int
    ) -> ProcessResult:
        program = await find_program(self._program, self._places)
        if program is None:
            msg = f"no trusted {self._program} program found"
            raise UnavailableError(msg)
        argv = [str(program), "--no-optional-locks", "-C", str(root), *args]
        env = {**child_environment(os.environ), **_FIXED_ENV}
        async with self._calls:
            return await run_process(argv, env=env, timeout_s=timeout_s, output_cap=cap)

    async def log(self, root: Path, base: str, since: float) -> str:
        """`git log` of `base` since the stamp, in the format the merge and revert rules read.

        Raises `GitUnavailableError` when git fails, takes over 60 s or prints over 32 MiB.
        """
        name = root.name
        args = ["log", LOG_FORMAT, f"--since={utc_stamp(since)}", "--end-of-options", base, "--"]
        try:
            done = await self._run(root, args, timeout_s=self._log_timeout_s, cap=self._output_cap)
        except UnavailableError as error:
            msg = f"cannot read the log of {name}: {error}"
            raise GitUnavailableError(msg) from None
        if done.timed_out:
            msg = f"cannot read the log of {name}: it took more than {self._log_timeout_s:g} s"
            raise GitUnavailableError(msg)
        if done.truncated:
            msg = f"cannot read the log of {name}: it is more than {self._output_cap} bytes"
            raise GitUnavailableError(msg)
        if done.code != 0:
            why = done.stderr.decode(errors="replace").strip() or f"git exited {done.code}"
            msg = f"cannot read the log of {name}: {why}"
            raise GitUnavailableError(msg)
        return done.stdout.decode(errors="replace")

    async def _read(self, root: Path, args: Sequence[str]) -> str | None:
        """The output of a small read, None when it failed in any way."""
        try:
            done = await self._run(root, args, timeout_s=self._read_timeout_s, cap=READ_CAP)
        except UnavailableError:
            return None
        return done.stdout.decode(errors="replace") if done.code == 0 else None

    async def autonomy_range(self, root: Path, commit: str) -> str | None:
        """`rev-list --parents c^1..c^2` of a merge: what it brought in; None for a squash."""
        args = ["rev-list", "--parents", "--end-of-options", f"{commit}^1..{commit}^2", "--"]
        return await self._read(root, args)

    async def branch_cut(self, root: Path, base: str, branch: str) -> float | None:
        """When the branch was cut: its reflog's oldest entry, else its oldest commit base lacks."""
        reflog = await self._read(
            root,
            [
                "reflog",
                "show",
                "--date=unix",
                "--format=%gd",
                "--end-of-options",
                f"refs/heads/{branch}",
                "--",
            ],
        )
        if (cut := _oldest_entry(reflog)) is not None:
            return cut
        own = await self._read(
            root, ["log", "--format=%ct", "--end-of-options", f"{base}..{branch}", "--"]
        )
        return _oldest(own)

    async def origin_web(self, root: Path) -> str | None:
        """The repository's GitHub address from its `origin` remote.

        None when it has no `origin` or one that is not on GitHub: a fact worth keeping.
        Raises `GitUnavailableError` when git cannot answer (a time-out, not a repository).
        """
        name = root.name
        try:
            done = await self._run(
                root,
                ["remote", "get-url", "origin"],
                timeout_s=self._origin_timeout_s,
                cap=READ_CAP,
            )
        except UnavailableError as error:
            msg = f"cannot read the origin of {name}: {error}"
            raise GitUnavailableError(msg) from None
        if done.timed_out or done.code not in (0, NO_SUCH_REMOTE):
            why = done.stderr.decode(errors="replace").strip() or "git did not answer"
            msg = f"cannot read the origin of {name}: {why}"
            raise GitUnavailableError(msg)
        return github_web(done.stdout.decode(errors="replace")) if done.code == 0 else None
