"""IO at the edge: the repository's files, the names of its tests and where it lives on the web.

Nothing here raises for a file it cannot read: a failure answers empty and is logged, so the
Memory page always renders. No call holds a database transaction (docs/async.md rule 20).
"""

import asyncio
import logging
import multiprocessing
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable

from anyio import CapacityLimiter, to_thread

from code_factory.memory_extras.models import Doc
from code_factory.memory_extras.rules import github_web, plain_cite
from code_factory.platform.errors import CodeFactoryError
from code_factory.platform.text import defined_functions, name_matches, python_nodes, rust_tests

log = logging.getLogger(__name__)

READ_LIMIT = 1 << 20
SOURCES = ("README.md", "CLAUDE.md", "docs/*.md")
TEST_SOURCES = (
    "*.rs", "*.py", "*.go", "*.ts", "*.tsx", "*.mts", "*.cts", "*.js", "*.jsx", "*.mjs", "*.cjs",
)  # fmt: skip
TEST_FILES = ("test_*.py", "*_test.py", "*_test.go", "*.test.*", "*.spec.*")
TEST_FOLDERS = frozenset({"tests", "test", "__tests__", "e2e", "spec"})
CALL_TIMEOUT_S = 10
SCAN_TIMEOUT_S = 30
CACHED_REPOSITORIES = 8
# Parsing 2.2 MB of test files took 266 ms on the sample repository (python_nodes parses every
# Python file) and would hold the loop's GIL in a thread, so a larger listing parses in a process.
PROCESS_FROM_BYTES = 512 * 1024
ORIGIN_TTL_S = 15

_FILES = CapacityLimiter(4)
_PARSING = CapacityLimiter(2)


@runtime_checkable
class GitFiles(Protocol):
    """The reads of the git service these adapters use."""

    async def head_commit(self, repository: str) -> str:
        """The commit checked out in the main checkout; empty on an unborn branch."""
        ...

    async def tracked_files(self, repository: str, patterns: list[str] | None = None) -> list[str]:
        """The files of the main checkout's `HEAD`, optionally limited by pathspecs."""
        ...

    async def read_text_below(self, root: Path, relative: str, limit: int) -> str | None:
        """A file below `root` read without following links."""
        ...

    async def remote_url(self, repository: str) -> str | None:
        """The URL of `origin`."""
        ...


_FAILURES = (CodeFactoryError, OSError, TimeoutError)


async def _read_file(git: GitFiles, root: Path, name: str) -> str | None:
    """The text of one tracked file; None when it is missing or this file alone cannot be read.

    A timeout is not caught here: it ends the whole scan.
    """
    try:
        return await git.read_text_below(root, name, READ_LIMIT)
    except CodeFactoryError, OSError:
        log.warning("%s could not be read", name, exc_info=True)
        return None


class RepositoryFiles:
    """The documents of a repository's main checkout that memory reads."""

    def __init__(self, git: GitFiles) -> None:
        self._git = git

    async def claude_md(self, root: Path) -> str:
        """The text of `CLAUDE.md`; empty when the file is missing or unreadable."""
        try:
            async with asyncio.timeout(CALL_TIMEOUT_S):
                return await self._git.read_text_below(root, "CLAUDE.md", READ_LIMIT) or ""
        except _FAILURES:
            log.warning("CLAUDE.md of %s could not be read", root, exc_info=True)
            return ""

    async def knowledge_files(self, repository: str, root: Path) -> list[Doc]:
        """README.md, CLAUDE.md and the markdown under docs/, as the main checkout tracks them."""
        try:
            async with asyncio.timeout(CALL_TIMEOUT_S):
                names = await self._git.tracked_files(repository, list(SOURCES))
                found = [await self._read(root, name) for name in sorted(set(names))]
        except _FAILURES:
            log.warning("the documents of %s could not be read", repository, exc_info=True)
            return []
        return [doc for doc in found if doc is not None]

    async def _read(self, root: Path, name: str) -> Doc | None:
        text = await _read_file(self._git, root, name)
        return None if text is None else Doc(path=name, text=text)

    async def cites_exist(self, root: Path, cites: Sequence[str]) -> frozenset[str]:
        """The plain cites that name a path existing below `root`."""
        plain = sorted({cite for cite in cites if plain_cite(cite)})

        def check() -> frozenset[str]:
            return frozenset(cite for cite in plain if (root / cite).exists())

        try:
            async with asyncio.timeout(CALL_TIMEOUT_S):
                return await to_thread.run_sync(check, limiter=_FILES, abandon_on_cancel=True)
        except _FAILURES:
            log.warning("the cites of %s could not be checked", root, exc_info=True)
            return frozenset()


def is_test_file(path: str) -> bool:
    """Whether a tracked file is read for test names: every `.rs`, and the test-named others."""
    parts = PurePosixPath(path)
    if parts.suffix == ".rs":
        return True
    in_tests = any(part in TEST_FOLDERS for part in parts.parent.parts)
    return in_tests or any(name_matches(parts.name, pattern) for pattern in TEST_FILES)


def names_in_test_file(path: str, text: str) -> list[str]:
    """The names of the tests a file defines, by its language."""
    suffix = PurePosixPath(path).suffix
    if suffix == ".rs":
        return rust_tests(text)
    if suffix == ".py":
        return [name for name, _ in python_nodes(text) if name.startswith("test")]
    if suffix == ".go":
        return [name for name in defined_functions(text) if name.startswith("Test")]
    return defined_functions(text)


def _parse_all(files: list[tuple[str, str]]) -> frozenset[str]:
    return frozenset(name for path, text in files for name in names_in_test_file(path, text))


class DefinedTests:
    """The names of the tests a repository defines, cached by the commit its main checkout holds.

    One listing runs per repository at a time: a caller that arrives while it runs waits for it
    and reads the cache.
    """

    def __init__(self, git: GitFiles) -> None:
        self._git = git
        self._cache: OrderedDict[str, tuple[str, frozenset[str]]] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}
        self._pool: ProcessPoolExecutor | None = None

    def close(self) -> None:
        """Stop the parsing process, when one started."""
        pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)

    async def defined(self, repository: str, root: Path) -> frozenset[str]:
        """The test names; empty when the repository cannot be read."""
        try:
            head = await self._git.head_commit(repository)
            async with self._locks.setdefault(repository, asyncio.Lock()):
                cached = self._cache.get(repository)
                if head and cached is not None and cached[0] == head:
                    self._cache.move_to_end(repository)
                    return cached[1]
                names = await self._scan(repository, root)
                if head:
                    self._remember(repository, head, names)
                return names
        except _FAILURES:
            log.warning("the tests of %s could not be listed", repository, exc_info=True)
            return frozenset()

    def _remember(self, repository: str, head: str, names: frozenset[str]) -> None:
        self._cache[repository] = (head, names)
        self._cache.move_to_end(repository)
        while len(self._cache) > CACHED_REPOSITORIES:
            self._cache.popitem(last=False)

    async def _scan(self, repository: str, root: Path) -> frozenset[str]:
        async with asyncio.timeout(SCAN_TIMEOUT_S):
            listed = await self._git.tracked_files(repository, list(TEST_SOURCES))
            files = []
            for name in (n for n in listed if is_test_file(n)):
                text = await _read_file(self._git, root, name)
                if text is not None:
                    files.append((name, text))
            if sum(len(text) for _, text in files) < PROCESS_FROM_BYTES:
                return await to_thread.run_sync(_parse_all, files, limiter=_PARSING)
            if self._pool is None:
                self._pool = ProcessPoolExecutor(
                    max_workers=1, mp_context=multiprocessing.get_context("spawn")
                )
            return await asyncio.get_running_loop().run_in_executor(self._pool, _parse_all, files)


class OriginWeb:
    """A repository's address on GitHub from its `origin`, remembered for a few seconds."""

    def __init__(self, git: GitFiles, clock: Callable[[], float] = time.monotonic) -> None:
        self._git = git
        self._clock = clock
        self._known: dict[str, tuple[float, str]] = {}

    async def web(self, repository: str) -> str:
        """The address, empty when `origin` is not a GitHub remote."""
        known = self._known.get(repository)
        if known is not None and self._clock() - known[0] < ORIGIN_TTL_S:
            return known[1]
        try:
            async with asyncio.timeout(CALL_TIMEOUT_S):
                remote = await self._git.remote_url(repository)
        except _FAILURES:
            log.warning("the origin of %s could not be read", repository, exc_info=True)
            return ""
        address = github_web(remote or "") or ""
        self._known[repository] = (self._clock(), address)
        return address
