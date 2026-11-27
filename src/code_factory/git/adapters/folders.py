"""File reads that never follow a link a run could plant, and the snapshot that judges a tree."""

import asyncio
import os
import stat
from collections.abc import Callable
from pathlib import Path

import anyio
import anyio.to_thread

from code_factory.git.models import FolderSnapshot
from code_factory.git.rules.folders import CLONE_TOKEN_FILE, named_folder
from code_factory.platform.errors import BadRequestError, UnavailableError

READ_TIMEOUT_S = 10.0
_files = anyio.CapacityLimiter(4)
_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def _read_below(root: str, relative: str, limit: int) -> str | None:
    parts = [part for part in relative.split("/") if part]
    if relative.startswith("/") or not parts or any(part in {".", ".."} for part in parts):
        msg = f"{relative} is not a path below {root}: it is absolute, empty or climbs"
        raise BadRequestError(msg)
    fds: list[int] = []
    try:
        current = os.open(root, _DIR)
        fds.append(current)
        for part in parts[:-1]:
            current = os.open(part, _DIR, dir_fd=current)
            fds.append(current)
        leaf = os.open(parts[-1], _FILE, dir_fd=current)
        fds.append(leaf)
        if not stat.S_ISREG(os.fstat(leaf).st_mode):
            msg = f"{relative} is not a regular file"
            raise BadRequestError(msg)
        data = os.read(leaf, limit + 1)
    except FileNotFoundError:
        return None
    except OSError as error:
        why = error.strerror
        msg = f"{relative} cannot be read below {root}: a link or unreadable part ({why})"
        raise BadRequestError(msg) from None
    finally:
        for fd in fds:
            os.close(fd)
    if len(data) > limit:
        msg = f"{relative} is over {limit} bytes"
        raise BadRequestError(msg)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        msg = f"{relative} is not UTF-8 text"
        raise BadRequestError(msg) from None


async def threaded[T](work: Callable[[], T], timeout_s: float = READ_TIMEOUT_S) -> T:
    """Run blocking file work in a worker thread of this module's limiter, under a time limit."""
    try:
        async with asyncio.timeout(timeout_s):
            return await anyio.to_thread.run_sync(work, limiter=_files, abandon_on_cancel=True)
    except TimeoutError:
        msg = f"a file read took more than {timeout_s:g} s; check the disk it is on"
        raise UnavailableError(msg) from None


async def exists(path: Path) -> bool:
    """Whether `path` exists, asked in a worker thread."""
    return await threaded(path.exists)


async def read_text_below(root: Path, relative: str, limit: int) -> str | None:
    """The text of `relative` below `root`, opened one part at a time without following links.

    `None` when the file is missing. A link, a fifo, a part that climbs, a file over `limit` bytes
    or text that is not UTF-8 raises `BadRequestError`.
    """
    return await threaded(lambda: _read_below(str(root), relative, limit))


def _text(path: Path) -> str | None:
    try:
        fd = os.open(path, _FILE)
    except OSError:
        return None
    try:
        return (
            os.read(fd, 4096).decode(errors="replace")
            if stat.S_ISREG(os.fstat(fd).st_mode)
            else None
        )
    except OSError:
        return None
    finally:
        os.close(fd)


def _real(path: Path) -> str:
    return os.path.realpath(path)


def _kind(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return "missing"
    if stat.S_ISLNK(mode):
        return "link"
    return "dir" if stat.S_ISDIR(mode) else "file"


def common_dir_of(checkout: Path) -> Path | None:
    """The git folder of the repository at `checkout` (itself possibly a linked worktree)."""
    dot_git = checkout / ".git"
    if _kind(dot_git) == "dir":
        return Path(_real(dot_git))
    admin = named_folder(_text(dot_git), "gitdir: ")
    if admin is None:
        return None
    common = (_text(Path(admin) / "commondir") or "").strip()
    return Path(os.path.normpath(Path(admin) / common)) if common else Path(admin)


def _nested(path: Path, tree: Path) -> bool:
    return any(
        (folder / ".git").exists()
        for folder in (path, *path.parents)
        if folder != tree and tree in folder.parents
    )


def snapshot_tree(path: Path, checkout: Path, at: Path | None = None) -> FolderSnapshot:
    """Read what `validate_tree` judges; `at` is a path inside the tree.

    Blocking: run it through `threaded`.
    """
    resolved = Path(_real(path))
    dot_git = resolved / ".git"
    text = _text(dot_git) if _kind(dot_git) == "file" else None
    admin = named_folder(text, "gitdir: ")
    admin_path = Path(admin) if admin is not None else None
    common = common_dir_of(checkout)
    info = dot_git / "objects/info"
    alternates = info / "alternates"
    return FolderSnapshot(
        resolved_path=str(resolved),
        nested_git=_nested(at or path, path),
        dot_git_kind=_kind(path / ".git"),
        dot_git_resolved=_real(path / ".git"),
        dot_git_text=text,
        admin_resolved=_real(admin_path) if admin_path else "",
        gitdir_text=_text(admin_path / "gitdir") if admin_path else None,
        commondir_text=_text(admin_path / "commondir") if admin_path else None,
        commondir_exists=(dot_git / "commondir").exists(),
        common_dir=str(common) if common else "",
        info_resolved=_real(info),
        alternates_resolved=_real(alternates),
        alternates_text=_text(alternates),
        alternates_exists=os.path.lexists(alternates),
        token_text=_text(dot_git / CLONE_TOKEN_FILE),
    )
