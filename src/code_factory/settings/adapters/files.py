"""Files below a repository root, read with no link followed.

Every folder of the path is opened with `O_NOFOLLOW` from the root's descriptor and so is the file,
so a link anywhere below the root refuses and cannot be swapped in between a check and the read.
The work runs in a worker thread under its own limiter, and a read that hangs times out.
"""

import asyncio
import os
import stat
from pathlib import Path, PurePosixPath
from typing import NamedTuple

import anyio
from anyio import CapacityLimiter, to_thread

TIMEOUT_S = 5.0
LIMITER_SLOTS = 4
_ROOT = os.O_RDONLY | os.O_DIRECTORY
_DIRECTORY = _ROOT | os.O_NOFOLLOW
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_CHUNK = 64 * 1024


class FileTimedOut(TimeoutError):  # noqa: N818  # a TimeoutError, named for what it reports
    """A strict call did not finish in time: the file's state is unknown, not missing."""


class FileKey(NamedTuple):
    """What a changed file changes: its modification time, its size and which file it is."""

    mtime_ns: int
    size: int
    inode: int


def _parts(relative: str) -> list[str] | None:
    path = PurePosixPath(relative)
    if "\0" in relative or path.is_absolute() or ".." in path.parts or path.parts in {(), (".",)}:
        return None
    return list(path.parts)


def _open_below(root: Path, relative: str) -> int | None:
    """A descriptor of the regular file `relative` below `root`, or None; the caller closes it."""
    parts = _parts(relative)
    if parts is None:
        return None
    try:
        directory = os.open(root, _ROOT)
    except TimeoutError:
        raise
    except OSError:
        return None
    try:
        for part in parts[:-1]:
            deeper = os.open(part, _DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = deeper
        descriptor = os.open(parts[-1], _FILE, dir_fd=directory)
    except TimeoutError:
        raise
    except OSError:
        return None
    finally:
        os.close(directory)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        return None
    return descriptor


def _read(root: Path, relative: str, limit: int) -> str | None:
    descriptor = _open_below(root, relative)
    if descriptor is None:
        return None
    try:
        chunks: list[bytes] = []
        size = 0
        while chunk := os.read(descriptor, _CHUNK):
            size += len(chunk)
            if size > limit:
                return None
            chunks.append(chunk)
    except TimeoutError:
        raise
    except OSError:
        return None
    finally:
        os.close(descriptor)
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError:
        return None


def _stat(root: Path, relative: str) -> FileKey | None:
    descriptor = _open_below(root, relative)
    if descriptor is None:
        return None
    try:
        found = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    return FileKey(found.st_mtime_ns, found.st_size, found.st_ino)


def _present(root: Path, relative: str) -> bool:
    """Whether anything, a link included, is at `relative`; folders above it are never links."""
    parts = _parts(relative)
    if parts is None:
        return False
    try:
        directory = os.open(root, _ROOT)
    except OSError:
        return False
    try:
        for part in parts[:-1]:
            deeper = os.open(part, _DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = deeper
        os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
    except OSError:
        return False
    finally:
        os.close(directory)
    return True


def _names(root: Path, relative: str) -> list[str]:
    """The names in the folder `relative` below `root`, sorted; none for a link or no folder."""
    parts = _parts(relative)
    if parts is None:
        return []
    try:
        directory = os.open(root, _ROOT)
    except OSError:
        return []
    try:
        for part in parts:
            deeper = os.open(part, _DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = deeper
        return sorted(os.listdir(directory))  # noqa: PTH208  # a descriptor, not a path
    except OSError:
        return []
    finally:
        os.close(directory)


class Files:
    """Reads and stats files below a root; anything unreadable is None, never an error."""

    def __init__(self, *, timeout: float = TIMEOUT_S) -> None:
        self._timeout = timeout
        self._limiter: CapacityLimiter | None = None

    def _slots(self) -> CapacityLimiter:
        if self._limiter is None:
            self._limiter = anyio.CapacityLimiter(LIMITER_SLOTS)
        return self._limiter

    async def read_below(
        self, root: Path, relative: str, limit: int, *, strict: bool = False
    ) -> str | None:
        """The UTF-8 text of a regular file below `root`, else None.

        The file is at most `limit` bytes and reached through no link. Past the timeout it is
        None, or raises `FileTimedOut` when `strict`.
        """
        try:
            async with asyncio.timeout(self._timeout):
                return await to_thread.run_sync(
                    _read, root, relative, limit, limiter=self._slots(), abandon_on_cancel=True
                )
        except TimeoutError:
            if strict:
                raise FileTimedOut(relative) from None
            return None

    async def stat(self, root: Path, relative: str, *, strict: bool = False) -> FileKey | None:
        """The change key of `relative` below `root`, None when `read_below` would be.

        Past the timeout it is None, or raises `FileTimedOut` when `strict`.
        """
        try:
            async with asyncio.timeout(self._timeout):
                return await to_thread.run_sync(
                    _stat, root, relative, limiter=self._slots(), abandon_on_cancel=True
                )
        except TimeoutError:
            if strict:
                raise FileTimedOut(relative) from None
            return None

    async def present(self, root: Path, relative: str) -> bool:
        """Whether something is at `relative` below `root`, whatever it is, a link included."""
        try:
            async with asyncio.timeout(self._timeout):
                return await to_thread.run_sync(
                    _present, root, relative, limiter=self._slots(), abandon_on_cancel=True
                )
        except TimeoutError:
            return False

    async def names(self, root: Path, relative: str) -> list[str]:
        """The sorted names in the folder `relative` below `root`; none when it is no folder."""
        try:
            async with asyncio.timeout(self._timeout):
                return await to_thread.run_sync(
                    _names, root, relative, limiter=self._slots(), abandon_on_cancel=True
                )
        except TimeoutError:
            return []
