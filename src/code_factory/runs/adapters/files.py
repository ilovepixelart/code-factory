"""Files of a run: its log tail, its exit file, and atomic writes, all in worker threads."""

import contextlib
import os
import shutil
import stat
import tempfile
from pathlib import Path

import anyio
import anyio.to_thread

_files = anyio.CapacityLimiter(4)
_PRIVATE = 0o600


def _open_regular(path: Path) -> int | None:
    """A descriptor for the regular file at `path`; `None` for a missing one, a link, a folder."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    if stat.S_ISREG(os.fstat(fd).st_mode):
        return fd
    os.close(fd)
    return None


def _tail(path: Path, limit: int) -> str | None:
    fd = _open_regular(path)
    if fd is None:
        return None
    with os.fdopen(fd, "rb") as handle:
        size = os.fstat(fd).st_size
        offset = max(0, size - limit)
        handle.seek(max(0, offset - 1))
        data = handle.read()
    if offset > 0:
        _, _, data = data.partition(b"\n")
    return data.decode(errors="replace")


async def read_tail(path: Path, limit: int) -> str | None:
    """The last `limit` bytes of a file from the start of a line; `None` when it is missing.

    A link is never followed.
    """
    return await anyio.to_thread.run_sync(_tail, path, limit, limiter=_files)


def _exit(path: Path) -> int | None:
    fd = _open_regular(path)
    if fd is None:
        return None
    with os.fdopen(fd, "rb") as handle:
        text = handle.read(64).decode(errors="replace").strip()
    try:
        return int(text)
    except ValueError:
        return None


async def read_exit(path: Path) -> int | None:
    """The exit code the run wrapper wrote; `None` when there is none or it is not a number."""
    return await anyio.to_thread.run_sync(_exit, path, limiter=_files)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w") as out:
            out.write(text)
        os.chmod(name, _PRIVATE)  # noqa: PTH101  # the temporary file's own descriptor is closed
        Path(name).replace(path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


async def write_atomic(path: Path, text: str) -> None:
    """Write `text` to a private file beside `path` and rename it over `path`."""
    await anyio.to_thread.run_sync(_write, path, text, limiter=_files)


async def remove(path: Path) -> None:
    """Delete a file; one already gone is not an error."""
    with contextlib.suppress(OSError):
        await anyio.to_thread.run_sync(lambda: path.unlink(missing_ok=True), limiter=_files)


async def remove_run_folder(path: Path) -> None:
    """Remove a run's private configuration once its process has stopped."""
    await anyio.to_thread.run_sync(lambda: shutil.rmtree(path, ignore_errors=True), limiter=_files)
