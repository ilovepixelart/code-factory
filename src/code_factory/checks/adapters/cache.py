"""A ticket's build cache and its snapshot's build folders.

They are moved, kept or removed, never through a link. A commit under check holds its own links,
so moving or deleting through one would reach outside the tree: every folder on the way must be a
real folder (`real_folders`). Every function here is synchronous and runs on a worker thread.
"""

import shutil
import stat
import subprocess
import sys
from pathlib import Path

import anyio

from code_factory.checks.rules import cache_key

CACHE = "check-cache"
LINUX_TARGET = "target/linux"
PNPM_STORE = "target/pnpm-store"
NAME = "a ticket's cache has a name"
CACHE_LIMITER = anyio.CapacityLimiter(2)  # a cache of several GB moves on a thread of its own
_COPY_TIMEOUT_S = 3600


def real_folders(base: Path, path: Path) -> bool:
    """Whether every folder of `path` below `base` that exists is a real folder, not a link.

    `base` itself is the caller's own. A part that does not exist yet is fine: nothing there can
    be followed.
    """
    try:
        below = path.relative_to(base)
    except ValueError:
        return False
    at = base
    for part in below.parts:
        at /= part
        try:
            info = at.lstat()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        if not stat.S_ISDIR(info.st_mode):
            return False
    return True


def _is_real_folder(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def cache_place(state: Path, key: str, name: str) -> Path | None:
    """Where the ticket's cache folder `name` is, when every folder down to it is a real one."""
    cache = state / CACHE / key / name
    return cache if real_folders(state, cache) else None


def move_dir(source: Path, target: Path) -> None:
    """Move a folder: renamed on one volume, else cloned where the system can and removed.

    A copy that fails leaves none.
    """
    try:
        source.rename(target)
    except OSError:
        _clone(source, target)


def _clone(source: Path, target: Path) -> None:
    clone = "-c" if sys.platform == "darwin" else "--reflink=auto"
    done = subprocess.run(  # noqa: S603  # fixed program, our own two paths
        ["/bin/cp", clone, "-R", "-p", str(source), str(target)],
        check=False,
        capture_output=True,
        timeout=_COPY_TIMEOUT_S,
    )
    if done.returncode == 0:
        shutil.rmtree(source, ignore_errors=True)
    else:
        shutil.rmtree(target, ignore_errors=True)


def adopt(state: Path, key: str, name: str, base: Path, place: Path) -> None:
    """Hand the ticket's cache folder `name` to the snapshot, `place` inside the tree at `base`.

    Moved, so a second snapshot at the same time builds cold. A cache that cannot move is left
    where it is, and none is handed into a link.
    """
    cache = cache_place(state, key, name)
    if cache is None or not _is_real_folder(cache) or not real_folders(base, place):
        return
    place.parent.mkdir(parents=True, exist_ok=True)
    move_dir(cache, place)


def discard(base: Path, place: Path) -> None:
    """Remove the snapshot's `place`, unless a folder on the way to it is a link."""
    if real_folders(base, place) and _is_real_folder(place):
        shutil.rmtree(place, ignore_errors=True)


def keep(state: Path, key: str, name: str, base: Path, place: Path) -> None:
    """Take the snapshot's `place` back as the ticket's cache folder `name`.

    Unless another snapshot filled it meanwhile; either way it is gone from the snapshot. Nothing
    is moved or removed when a folder on the way is a link.
    """
    cache = cache_place(state, key, name)
    if cache is None:
        discard(base, place)
        return
    if not real_folders(base, place) or not _is_real_folder(place):
        return
    if not cache.exists() and not cache.is_symlink():
        cache.parent.mkdir(parents=True, exist_ok=True)
        move_dir(place, cache)
    discard(base, place)


def forget(state: Path, ticket_id: str) -> None:
    """Remove the whole cache of the ticket.

    Nothing is removed when there is none or when the cache folder or the one it sits in is a
    link. The path is built here from the state folder and `cache_key` only.
    """
    key = cache_key(ticket_id)
    if not key:
        raise ValueError(NAME)
    folder = state / CACHE / key
    if real_folders(state, folder) and _is_real_folder(folder):
        shutil.rmtree(folder)


def folders(state: Path) -> list[tuple[str, Path]]:
    """The ticket caches kept under `state`: real folders named as `cache_key` names them."""
    base = state / CACHE
    if not real_folders(state, base):
        return []
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return []
    return [
        (entry.name, entry)
        for entry in entries
        if _is_real_folder(entry) and entry.name and cache_key(entry.name) == entry.name
    ]
