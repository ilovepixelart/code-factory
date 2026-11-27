"""The checks logs in the state folder: where they are, which may be opened, and their ages."""

import os
import stat
from pathlib import Path

import anyio
import anyio.to_thread

from code_factory.checks.rules import log_name, log_name_any, log_name_ok

LOG_FOLDER = "checks"
MAX_READ = 16 * 1024 * 1024
_files = anyio.CapacityLimiter(4)


def _read_tail(path: Path, cap: int) -> str | None:
    try:
        with path.open("rb") as handle:
            size = os.fstat(handle.fileno()).st_size
            handle.seek(max(size - cap, 0))
            return handle.read(cap).decode("utf-8", errors="replace")
    except OSError:
        return None


def _read_range(path: Path, offset: int, size: int) -> tuple[bytes, int]:
    with path.open("rb") as handle:
        total = os.fstat(handle.fileno()).st_size
        handle.seek(min(offset, total))
        return handle.read(size), total


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _within(folder: Path, path: Path, repository: str, subject: str) -> Path | None:
    try:
        real_folder = folder.resolve(strict=True)
        real = path.resolve(strict=True)
        regular = stat.S_ISREG(real.stat().st_mode)
    except OSError:
        return None
    named = log_name_ok(real.name, repository, subject)
    return real if regular and named and real.parent == real_folder else None


def _within_any(folder: Path, path: Path) -> Path | None:
    try:
        real_folder = folder.resolve(strict=True)
        real = path.resolve(strict=True)
        regular = stat.S_ISREG(real.stat().st_mode)
    except OSError:
        return None
    return real if regular and log_name_any(real.name) and real.parent == real_folder else None


def _older_than(folder: Path, cutoff: float) -> list[Path]:
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return []
    found = []
    for entry in entries:
        try:
            info = entry.lstat()
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode) and entry.suffix == ".log" and info.st_mtime < cutoff:
            found.append(entry)
    return found


def _remove(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


class LogFiles:
    """The logs under `<state>/checks`."""

    def __init__(self, state_dir: Path) -> None:
        self._folder = state_dir / LOG_FOLDER

    @property
    def folder(self) -> Path:
        """Where the logs are written."""
        return self._folder

    def path_for(self, repository: str, subject: str, second: int) -> Path:
        """The log of a run of `subject` begun at `second`."""
        return self._folder / log_name(repository, subject, second)

    async def text_of(self, path: Path) -> str | None:
        """The log's text (its last 16 MiB when longer); None when it cannot be read."""
        return await anyio.to_thread.run_sync(_read_tail, path, MAX_READ, limiter=_files)

    async def append(self, path: Path, text: str) -> None:
        """Add `text` to the log."""
        await anyio.to_thread.run_sync(_append, path, text, limiter=_files)

    async def write(self, path: Path, text: str) -> None:
        """Replace the log's content."""
        await anyio.to_thread.run_sync(_write, path, text, limiter=_files)

    async def within(self, repository: str, subject: str, named: str) -> Path | None:
        """The log `named` resolved, when it is a log of `subject` right in the logs folder.

        A file outside the folder, a link that leads elsewhere, anything that is no regular file
        and another ticket's or repository's log, which the folder also holds, are none.
        """
        return await anyio.to_thread.run_sync(
            _within, self._folder, Path(named), repository, subject, limiter=_files
        )

    async def within_any(self, named: str) -> Path | None:
        """The log `named` resolved, when it is any ticket's or main's log right in the folder."""
        return await anyio.to_thread.run_sync(
            _within_any, self._folder, Path(named), limiter=_files
        )

    async def page(self, path: Path, offset: int, size: int) -> tuple[str, int, int]:
        """`size` bytes of the log from `offset`: the text, the log's size, the next offset."""
        data, total = await anyio.to_thread.run_sync(
            _read_range, path, offset, size, limiter=_files
        )
        return data.decode("utf-8", errors="replace"), total, min(offset, total) + len(data)

    async def older_than(self, cutoff: float) -> list[Path]:
        """The logs last written before `cutoff` (a time in seconds)."""
        return await anyio.to_thread.run_sync(_older_than, self._folder, cutoff, limiter=_files)

    async def remove(self, paths: list[Path]) -> None:
        """Delete the logs."""
        await anyio.to_thread.run_sync(_remove, paths, limiter=_files)
