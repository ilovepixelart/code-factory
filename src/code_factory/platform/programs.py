"""Finding a program a run cannot have replaced.

A run writes in its clone and in temporary folders, so a program found by name through a `PATH`
folder it can write, or through a link in one, is code the run chose. A program is therefore taken
only from an absolute `PATH` folder that only root or the user can write, outside `places` (the
folders a run may write: tracked repositories, the state folder, `/tmp`, `/var/tmp`), through no
link that sits in a folder the run could change. What is returned is the file itself, resolved:
start that, never the name.

The functions here are synchronous and read the filesystem; `find_program` and `find_path` run
them in a worker thread under their own limiter and a time limit. Children never inherit the
variables with which git names a repository (`child_environment`).
"""

import asyncio
import os
import stat
from collections.abc import Callable, Iterable, Mapping, Sequence
from functools import partial
from pathlib import Path

import anyio
import anyio.to_thread

from code_factory.platform.errors import UnavailableError

MOST_LINKS = 32  # what macOS follows on the way to a file (MAXSYMLINKS)
NVMRC_BYTES = 32
FILE_LOOKUP_TIMEOUT_S = 10.0
# The variables git sets to name a repository; a hook's children inherit them and git obeys them
# over `-C`, so a git started by the board must not.
REPOSITORY_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
)
# The system's shared temporary folders: every run may write there, so they are always among the
# `places` a program is never taken from.
TEMPORARY_FOLDERS = (Path("/tmp"), Path("/var/tmp"))  # noqa: S108
_STICKY = 0o1000
_OTHERS_WRITE = 0o002
_GROUP_WRITE = 0o020
_ANY_EXECUTE = 0o111

_files = anyio.CapacityLimiter(4)


def child_environment(env: Mapping[str, str]) -> dict[str, str]:
    """`env` without the variables that name a repository."""
    return {name: value for name, value in env.items() if name not in REPOSITORY_VARIABLES}


def writers_known_as(owner: int, mode: int, user: int) -> bool:
    """Whether only root or `user` can write what is owned by `owner` with `mode`.

    Others never may; the group may only when `user` owns it (Homebrew's folders are the user's
    and the admin group's). A root-owned entry the group can write has writers nobody can name.
    """
    own = owner == user
    return (own or owner == 0) and not mode & _OTHERS_WRITE and (own or not mode & _GROUP_WRITE)


def _writers_known(found: os.stat_result) -> bool:
    return writers_known_as(found.st_uid, found.st_mode, os.getuid())


def _holds_safely(folder: Path) -> bool:
    """Whether only root or the user can rename what `folder` holds.

    Its writers are known, or it is sticky and theirs (`/tmp`), where only an entry's owner may
    rename it.
    """
    try:
        found = folder.stat()
    except OSError:
        return False
    owned = found.st_uid in {0, os.getuid()}
    return _writers_known(found) or (bool(found.st_mode & _STICKY) and owned)


def _outside(real: Path, places: Iterable[Path]) -> bool:
    return not any(real.is_relative_to(place.resolve()) for place in places)


def _trusted_folder(folder: Path, places: Sequence[Path]) -> bool:
    """Whether `folder` is outside `places`, its writers are known, and so is everything above it.

    Every folder above it, as written and with links resolved, must hold it safely (whoever
    writes a parent can rename the folder away), and every link on the way sits in a trusted one.
    """
    try:
        real = folder.resolve(strict=True)
        found = folder.stat()
    except OSError, RuntimeError:
        return False
    return (
        _writers_known(found)
        and all(_holds_safely(parent) for parent in (*folder.parents, *real.parents))
        and _outside(real, places)
        and _trusted_way(folder, places) is not None
    )


def _parts(path: Path) -> list[str]:
    """The names of `path`, the first on top of a stack (the end of the list)."""
    return [part for part in reversed(path.parts) if part not in {"/", "."}]


def _trusted_way(path: Path, places: Sequence[Path]) -> Path | None:
    """`path` with every link resolved one at a time from `/`, or None.

    None when a link sits in a folder `_trusted_folder` passes over (its writers can point it
    elsewhere), or when the way holds more than `MOST_LINKS` links, as a loop does.
    """
    resolved = Path("/")
    rest = _parts(path)
    links = 0
    while rest:
        part = rest.pop()
        if part == "..":
            resolved = resolved.parent
            continue
        following = resolved / part
        try:
            target = following.readlink()
        except OSError:
            resolved = following
            continue
        links += 1
        if links > MOST_LINKS or not _trusted_folder(resolved, places):
            return None
        if target.is_absolute():
            resolved = Path("/")
        rest.extend(_parts(target))
    return resolved


def _startable(path: Path) -> bool:
    """A regular file, links followed, with an execute bit: what the system would start."""
    try:
        found = path.stat()
    except OSError:
        return False
    return stat.S_ISREG(found.st_mode) and bool(found.st_mode & _ANY_EXECUTE)


def _trusted_file(path: Path, places: Sequence[Path]) -> Path | None:
    target = _trusted_way(path, places)
    if target is None or not _startable(target):
        return None
    try:
        found = target.stat()
    except OSError:
        return None
    if _writers_known(found) and _trusted_folder(target.parent, places):
        return target
    return None


def _absolute_folders(places: Sequence[Path], search_path: str | None) -> list[Path]:
    raw = os.environ.get("PATH", "") if search_path is None else search_path
    folders = (Path(entry) for entry in raw.split(os.pathsep) if entry)
    return [
        folder for folder in folders if folder.is_absolute() and _trusted_folder(folder, places)
    ]


def trusted_program(
    name: str,
    places: Sequence[Path],
    *,
    search_path: str | None = None,
    pinned: Path | None = None,
) -> Path | None:
    """The file to start for `name`, or None.

    An absolute `name` is taken as it is when the system would start it. Otherwise the first
    trusted file of that name: in `pinned` first, then in each trusted absolute folder of
    `search_path` (default `$PATH`), in order.
    """
    if Path(name).is_absolute():
        return Path(name) if _startable(Path(name)) else None
    if pinned is not None and (found := _trusted_file(pinned / name, places)):
        return found
    for folder in _absolute_folders(places, search_path):
        if found := _trusted_file(folder / name, places):
            return found
    return None


def absolute_path(
    places: Sequence[Path], *, search_path: str | None = None, pinned: Path | None = None
) -> str:
    """`PATH` cut to its trusted absolute folders (resolved), `pinned` first when given.

    What a check, a hook or a run starts with, so a relative folder cannot resolve a name inside
    the folder a program starts in, which a run may have written.
    """
    folders = [folder.resolve() for folder in _absolute_folders(places, search_path)]
    if pinned is not None:
        folders = [pinned, *(folder for folder in folders if folder != pinned)]
    return os.pathsep.join(str(folder) for folder in folders)


def _pinned_version(text: str) -> str | None:
    """The version a `.nvmrc` pins: dot-separated digits, a leading `v` allowed; nothing else."""
    version = text.strip().removeprefix("v")
    parts = version.split(".")
    return version if all(part.isascii() and part.isdigit() for part in parts) else None


def pinned_node(
    nvmrc: str | None, places: Sequence[Path], *, home: Path | None = None
) -> Path | None:
    """The `bin` folder of the node install a checkout's `.nvmrc` text pins, when it is trusted.

    Looked up under `<home>/.nvm/versions/node`. The login shell's default node may be another,
    which lacks the tools the pinned one holds. A text over `NVMRC_BYTES` or that is not a plain
    version reaches no path.
    """
    if nvmrc is None or len(nvmrc.encode()) > NVMRC_BYTES:
        return None
    version = _pinned_version(nvmrc)
    base = Path.home() if home is None else home
    if version is None or not base.is_absolute():
        return None
    folder = base / ".nvm/versions/node" / f"v{version}" / "bin"
    return folder if _trusted_folder(folder, places) else None


async def _threaded[T](work: Callable[[], T]) -> T:
    """Run a filesystem walk in a worker thread of its own limiter, under a time limit."""
    try:
        async with asyncio.timeout(FILE_LOOKUP_TIMEOUT_S):
            return await anyio.to_thread.run_sync(work, limiter=_files, abandon_on_cancel=True)
    except TimeoutError:
        msg = "the lookup of a trusted program took more than 10 s"
        raise UnavailableError(msg) from None


async def find_program(
    name: str,
    places: Sequence[Path],
    *,
    search_path: str | None = None,
    pinned: Path | None = None,
) -> Path | None:
    """`trusted_program` off the event loop."""
    return await _threaded(
        partial(trusted_program, name, places, search_path=search_path, pinned=pinned)
    )


async def find_pinned_node(
    nvmrc: str | None, places: Sequence[Path], *, home: Path | None = None
) -> Path | None:
    """`pinned_node` off the event loop."""
    return await _threaded(partial(pinned_node, nvmrc, places, home=home))


async def find_path(
    places: Sequence[Path], *, search_path: str | None = None, pinned: Path | None = None
) -> str:
    """`absolute_path` off the event loop."""
    return await _threaded(partial(absolute_path, places, search_path=search_path, pinned=pinned))
