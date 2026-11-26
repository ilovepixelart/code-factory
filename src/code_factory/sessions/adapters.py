"""IO at the edge: the spool, git's files, transcripts and the redaction file.

Every call that touches the disk runs in a worker thread under a limiter of its own, so one kind
of work cannot starve another. No process, git binary, network or keychain.
"""

import asyncio
import contextlib
import os
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from anyio import CapacityLimiter, to_thread

from code_factory.sessions.models import Checkout
from code_factory.sessions.rules import checkout as rules

MAX_LINE_BYTES = 8 * 1024 * 1024
TRANSCRIPT_CHUNK_BYTES = 4 * 1024 * 1024
# A transcript line past this is unreadable rather than held whole.
TRANSCRIPT_LINE_LIMIT_BYTES = 64 * 1024 * 1024
CHECKOUT_TTL_S = 5.0
_SKIP_BLOCK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class SpoolLine:
    """One whole line of a spool: where it starts and its bytes without the line break."""

    offset: int
    data: bytes
    too_long: bool = False


@dataclass(frozen=True, slots=True)
class SpoolRead:
    """The whole lines read from an offset, and the offset after the last of them."""

    lines: list[SpoolLine]
    end: int


def _read_spool(path: Path, offset: int, max_line: int) -> SpoolRead:
    try:
        return _read_lines(path, offset, max_line)
    except FileNotFoundError:
        return SpoolRead([], offset)  # pruned or removed since it was listed


def _read_lines(path: Path, offset: int, max_line: int) -> SpoolRead:
    with path.open("rb") as handle:
        handle.seek(offset)
        chunk = handle.read(max_line + 1)
        cut = chunk.rfind(b"\n") + 1
        if cut == 0:
            if len(chunk) <= max_line:
                return SpoolRead([], offset)  # a line still being written
            return _skip_long_line(handle, offset, chunk)
        lines = []
        start = 0
        for line in chunk[:cut].split(b"\n")[:-1]:
            lines.append(SpoolLine(offset + start, line))
            start += len(line) + 1
        return SpoolRead(lines, offset + cut)


def _skip_long_line(handle, offset: int, head: bytes) -> SpoolRead:  # noqa: ANN001  # a binary file
    """A line past the limit: rejected without being held; once its end is known."""
    length = len(head)
    while True:
        block = handle.read(_SKIP_BLOCK)
        if not block:
            return SpoolRead([], offset)  # no end yet: it may still be written
        found = block.find(b"\n")
        if found >= 0:
            return SpoolRead(
                [SpoolLine(offset, head[:200], too_long=True)], offset + length + found + 1
            )
        length += len(block)


class SpoolReader:
    """The capture spool: one `.jsonl` file per session, appended by the hook."""

    def __init__(
        self,
        directory: Path,
        *,
        max_line: int = MAX_LINE_BYTES,
        limiter: CapacityLimiter | None = None,
    ) -> None:
        self._directory = directory
        self._max_line = max_line
        self._limiter = limiter or CapacityLimiter(2)

    @property
    def directory(self) -> Path:
        """Where the spool files are."""
        return self._directory

    async def names(self) -> list[str]:
        """The spool file names in name order; none when the folder does not exist."""
        return await to_thread.run_sync(self._names, limiter=self._limiter)

    def _names(self) -> list[str]:
        try:
            with os.scandir(self._directory) as entries:
                return sorted(e.name for e in entries if e.name.endswith(".jsonl"))
        except FileNotFoundError:
            return []

    async def stats(self, names: Iterable[str]) -> dict[str, tuple[int, float]]:
        """The size and modification time of each named file that still exists."""
        return await to_thread.run_sync(self._stats, list(names), limiter=self._limiter)

    def _stats(self, names: list[str]) -> dict[str, tuple[int, float]]:
        found = {}
        for name in names:
            with contextlib.suppress(OSError):
                status = (self._directory / name).stat()
                found[name] = (status.st_size, status.st_mtime)
        return found

    async def read_from(self, name: str, offset: int) -> SpoolRead:
        """The whole lines of a spool from `offset`, at most about the limit of bytes.

        A line over the limit comes back as one `too_long` line holding only its head.
        """
        return await to_thread.run_sync(
            _read_spool, self._directory / name, offset, self._max_line, limiter=self._limiter
        )

    async def remove(self, expected: Mapping[str, tuple[int, float]]) -> list[str]:
        """Delete the named files that still have the size and modification time given.

        A file the hook appended to since is kept. Returns the names that are gone, which includes
        a file that was already missing.
        """
        return await to_thread.run_sync(self._remove, dict(expected), limiter=self._limiter)

    def _remove(self, expected: dict[str, tuple[int, float]]) -> list[str]:
        gone = []
        for name, seen in expected.items():
            path = self._directory / name
            try:
                status = path.stat()
                if (status.st_size, status.st_mtime) != seen:
                    continue
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                continue
            gone.append(name)
        return gone


def _is_dir_or_file(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _locate(cwd: str) -> Checkout | None:
    """The repository and branch around `cwd`, by the rules over git's own files."""
    if not cwd:
        return None
    here = Path(cwd)
    found = next(
        (folder for folder in (here, *here.parents) if _is_dir_or_file(folder / ".git")), None
    )
    if found is None:
        return None
    tree = Path(rules.tree_checkout(PurePosixPath(found)))
    main = tree
    pointer = _read_text(tree / ".git") if (tree / ".git").is_file() else None
    if pointer is not None:
        gitdir = rules.main_of_worktree_gitdir(rules.pointer_target(pointer, PurePosixPath(tree)))
        main = Path(gitdir) if gitdir is not None else tree
    with contextlib.suppress(OSError):
        main = main.resolve()
    return Checkout(main.name, _branch(found))


def _branch(root: Path) -> str:
    git = root / ".git"
    if git.is_file():
        text = _read_text(git)
        target = None if text is None else rules.gitdir_of(text, PurePosixPath(root))
        if target is None:
            return ""
        git = Path(target)
    head = _read_text(git / "HEAD")
    return "" if head is None else rules.branch_of_head(head)


class CheckoutLocator:
    """Where a session's working folder sits: its repository and branch, cached per folder."""

    def __init__(
        self,
        *,
        ttl: float = CHECKOUT_TTL_S,
        monotonic: Callable[[], float] = time.monotonic,
        limiter: CapacityLimiter | None = None,
    ) -> None:
        self._ttl = ttl
        self._monotonic = monotonic
        self._limiter = limiter or CapacityLimiter(4)
        self._cache: dict[str, tuple[float, Checkout | None]] = {}

    async def locate(self, cwd: str) -> Checkout | None:
        """The checkout around `cwd`; None for a missing folder or one inside no repository."""
        now = self._monotonic()
        cached = self._cache.get(cwd)
        if cached is not None and cached[0] > now:
            return cached[1]
        found = await to_thread.run_sync(_locate, cwd, limiter=self._limiter)
        self._cache[cwd] = (now + self._ttl, found)
        return found

    def expire(self) -> None:
        """Drop the answers whose time has passed."""
        now = self._monotonic()
        self._cache = {cwd: item for cwd, item in self._cache.items() if item[0] > now}


class TranscriptReader:
    """The agent runtime's transcripts, read in pieces."""

    def __init__(self, *, limiter: CapacityLimiter | None = None) -> None:
        self._limiter = limiter or CapacityLimiter(4)

    async def stat(self, path: str) -> tuple[int, int] | None:
        """The size and modification time (ns) of a file; None when it cannot be read."""
        return await to_thread.run_sync(self._stat, path, limiter=self._limiter)

    @staticmethod
    def _stat(path: str) -> tuple[int, int] | None:
        try:
            status = Path(path).stat()
        except OSError:
            return None
        return status.st_size, status.st_mtime_ns

    async def read_chunk(self, path: str, offset: int, size: int) -> bytes:
        """Up to `size` bytes from `offset`; nothing when the file cannot be read."""
        return await to_thread.run_sync(self._read, path, offset, size, limiter=self._limiter)

    @staticmethod
    def _read(path: str, offset: int, size: int) -> bytes:
        try:
            with Path(path).open("rb") as handle:
                handle.seek(offset)
                return handle.read(size)
        except OSError:
            return b""

    async def listdir(self, folder: str) -> list[str]:
        """The names in a folder; none when it does not exist."""
        return await to_thread.run_sync(self._listdir, folder, limiter=self._limiter)

    @staticmethod
    def _listdir(folder: str) -> list[str]:
        try:
            return os.listdir(folder)  # noqa: PTH208  # names only, in a worker thread
        except OSError:
            return []


class RedactionFile:
    """`redaction.json` in the state folder, replaced whole and owner-only."""

    NAME = "redaction.json"

    def __init__(self, state_dir: Path, *, limiter: CapacityLimiter | None = None) -> None:
        self._state_dir = state_dir
        self._limiter = limiter or CapacityLimiter(1)
        self._lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        """Where the hook reads it."""
        return self._state_dir / self.NAME

    async def write(self, text: str) -> None:
        """Write the file through a temporary one and a rename, mode 0600; one write at a time."""
        async with self._lock:
            await to_thread.run_sync(self._write, text, limiter=self._limiter)

    def _write(self, text: str) -> None:
        self._state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self._state_dir / f".{self.NAME}.{os.getpid()}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
            temporary.replace(self.path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
