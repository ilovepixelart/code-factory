"""The team module's only IO: the git reads behind the Team page's cycle and first commits.

No `gh`, network or credential access. A failed, timed-out or over-long git answers empty and
logs a warning, never fails the page.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import NamedTuple

logger = logging.getLogger(__name__)

DAY = 86_400
_TAGS = ("for-each-ref", "refs/tags", "--format=%(refname:short)%09%(creatordate:unix)")
_GRACE = 2.0


class _Cached(NamedTuple):
    expires: float
    key: int
    value: str


class GitFacts:
    """Tags and first commits of repositories, kept for `ttl` seconds per repository.

    One git runs per repository at a time (the answers are shared), and at most `concurrency`
    run across repositories. `clock` is monotonic seconds; a test drives expiry with its own.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        git: str = "git",
        clock: Callable[[], float] = time.monotonic,
        ttl: float = 15.0,
        timeout: float = 10.0,
        limit: int = 4 * 1024 * 1024,
        concurrency: int = 4,
    ) -> None:
        self._git = git
        self._clock = clock
        self._ttl = ttl
        self._timeout = timeout
        self._limit = limit
        self._slots = asyncio.Semaphore(concurrency)
        self._locks: dict[str, asyncio.Lock] = {}
        self._cache: dict[tuple[str, str], _Cached] = {}
        self._reaping: set[asyncio.Task[None]] = set()

    async def tags(self, repository: str) -> list[tuple[str, float]]:
        """The repository's tags with the moments they were made; empty when git fails."""
        text = await self._cached(repository, "tags", 0, ["-C", repository, *_TAGS])
        found: list[tuple[str, float]] = []
        for line in text.splitlines():
            name, tab, stamp = line.partition("\t")
            try:
                moment = float(stamp.strip())
            except ValueError:
                continue
            if tab:
                found.append((name, moment))
        return found

    async def first_commit_log(self, repository: str, since: float) -> str:
        """`%at<TAB>%s` of every commit since the UTC day of `since`; empty when git fails."""
        day = int(since // DAY * DAY)
        args = ["-C", repository, "log", "--all", f"--since=@{day}", "--format=%at%x09%s", "--"]
        return await self._cached(repository, "log", day, args)

    async def _cached(self, repository: str, kind: str, key: int, args: list[str]) -> str:
        lock = self._locks.setdefault(repository, asyncio.Lock())
        async with lock:
            kept = self._cache.get((repository, kind))
            if kept is not None and kept.key == key and self._clock() < kept.expires:
                return kept.value
            value = await self._run(repository, args)
            self._cache[(repository, kind)] = _Cached(self._clock() + self._ttl, key, value)
            return value

    async def _run(self, repository: str, args: list[str]) -> str:
        async with self._slots:
            try:
                process = await asyncio.create_subprocess_exec(
                    self._git,
                    *args,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            except OSError as error:
                logger.warning("git %s could not start in %s: %s", args[2], repository, error)
                return ""
            try:
                async with asyncio.timeout(self._timeout):
                    output, cut = await self._read(process)
                    code = None if cut else await process.wait()
            except TimeoutError:
                logger.warning(
                    "git %s did not finish within %g s in %s", args[2], self._timeout, repository
                )
                return ""
            finally:
                await asyncio.shield(self._reap_owned(process))
        if cut:
            logger.warning("git %s output passed %d bytes in %s", args[2], self._limit, repository)
            return ""
        if code not in {0, None}:
            logger.warning("git %s failed in %s (exit %s)", args[2], repository, code)
            return ""
        return output.decode("utf-8", errors="replace")

    def _reap_owned(self, process: asyncio.subprocess.Process) -> asyncio.Task[None]:
        """Reap in a task this object holds: a second cancellation must not orphan it."""
        task = asyncio.create_task(_reap(process))
        self._reaping.add(task)
        task.add_done_callback(self._reaping.discard)
        return task

    async def _read(self, process: asyncio.subprocess.Process) -> tuple[bytes, bool]:
        """Output up to the cap and whether more followed; `_reap` stops a process that goes on."""
        stream = process.stdout
        assert stream is not None  # noqa: S101  # stdout=PIPE above
        chunks = bytearray()
        while len(chunks) <= self._limit and (chunk := await stream.read(65_536)):
            chunks += chunk
        return bytes(chunks[: self._limit]), len(chunks) > self._limit


async def _reap(process: asyncio.subprocess.Process) -> None:
    """Stop the child if it still runs: terminate, a short grace, kill; always wait for it.

    The unread rest of its output is drained so the pipe's transport closes with the process.
    """
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
        try:
            async with asyncio.timeout(_GRACE):
                await process.wait()
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
    await process.wait()
    if process.stdout is not None:
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(_GRACE):
                while await process.stdout.read(65_536):
                    pass
