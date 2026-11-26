"""Where a mount path leads on this machine, found without ever probing an automount root.

The path is walked one component at a time with `lstat` and `readlink`; a component or link target
on an automount root is refused before it is touched, so the walk cannot hang on or reach a
network. Each resolution runs in a daemon thread bounded by a timeout and a process-wide budget of
workers, and a scan has one deadline after which nothing more is resolved.
"""

import contextlib
import errno
import os
import stat
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import PurePosixPath

from code_factory.settings.rules.secrets import VALIDATION_HOME, Unjudged, on_automount_root

RESOLVE_TIMEOUT_S = 2.0
SCAN_DEADLINE_S = 6.0
RESOLVE_WORKERS = 4
MAX_LINKS = 40
_SLOTS = threading.BoundedSemaphore(RESOLVE_WORKERS)
_ROOT = PurePosixPath("/")


class AutomountReached(OSError):  # noqa: N818  # an OSError a caller handles as a failed lookup
    """The path, or a link on it, leads onto an automount root."""


def walk_realpath(
    path: str,
    lstat: Callable[[str], os.stat_result] = os.lstat,
    readlink: Callable[[str], str] = os.readlink,
    *,
    refuse: Callable[[PurePosixPath], bool] = on_automount_root,
) -> str:
    """`os.path.realpath(path, strict=ALLOW_MISSING)` of an absolute `path`, walked by hand.

    Raises `AutomountReached` before `lstat` or `readlink` is asked about a path `refuse` names
    (by default an automount root), and
    `OSError` for a loop of links or a lookup that fails for another reason than a missing name.
    """
    pending = deque(path.split("/"))
    resolved = _ROOT
    folder = True
    missing = False
    links = 0
    while pending:
        name = pending.popleft()
        if not folder:
            raise NotADirectoryError(errno.ENOTDIR, "not a directory", str(resolved))
        if name in {"", "."}:
            continue
        if name == "..":
            if missing:
                # No parent of a missing name exists; a textual one could skip a link.
                raise FileNotFoundError(errno.ENOENT, "no parent of a missing name", path)
            resolved = resolved.parent
            continue
        candidate = resolved / name
        if refuse(candidate):
            raise AutomountReached(errno.EACCES, "an automount root", str(candidate))
        resolved = candidate
        try:
            mode = lstat(str(candidate)).st_mode
        except FileNotFoundError:
            missing = True
            continue
        if not stat.S_ISLNK(mode):
            folder = stat.S_ISDIR(mode)
            continue
        links += 1
        if links > MAX_LINKS:
            raise OSError(errno.ELOOP, "Too many levels of symbolic links", path)
        target = readlink(str(candidate))
        resolved = _ROOT if target.startswith("/") else candidate.parent
        pending.extendleft(reversed(target.split("/")))
    return str(resolved)


class LocalResolver:
    """Resolves paths below `roots` for one scan; see `local_resolver`."""

    def __init__(
        self,
        roots: Sequence[PurePosixPath],
        timeout: float,
        deadline_s: float,
        clock: Callable[[], float],
        follow: Callable[[str], str] | None,
    ) -> None:
        self._roots = [str(root).casefold() for root in roots]
        self._timeout = timeout
        self._clock = clock
        self._deadline = clock() + deadline_s
        self._follow = follow or partial(walk_realpath, refuse=self._refuses)
        self._memo: dict[PurePosixPath, PurePosixPath] = {}

    def _local(self, path: PurePosixPath) -> bool:
        text = str(path).casefold()
        return any(text == r or text.startswith(r.rstrip("/") + "/") for r in self._roots)

    def _refuses(self, path: PurePosixPath) -> bool:
        """An automount root, or `/home` or a folder of it that holds no local root or is in none.

        `/home` can be an automount map, and a link must not lead into it from elsewhere.
        """
        if on_automount_root(path):
            return True
        text = str(path).casefold()
        home = str(VALIDATION_HOME).casefold()
        if text != home and not text.startswith(home + "/"):
            return False
        return not (
            self._local(path)
            or any(root.startswith(text.rstrip("/") + "/") for root in self._roots)
        )

    def __call__(self, path: PurePosixPath) -> PurePosixPath:
        """Where `path` leads, `/` when that cannot be told; `Unjudged` past the deadline."""
        if self._clock() >= self._deadline:
            raise Unjudged
        if not self._local(path):
            return path
        if path not in self._memo:
            self._memo[path] = self._resolve(path)
        return self._memo[path]

    def _resolve(self, path: PurePosixPath) -> PurePosixPath:
        if not _SLOTS.acquire(blocking=False):
            return _ROOT
        found: list[str] = []

        def work() -> None:
            try:
                with contextlib.suppress(ValueError, OSError):
                    found.append(self._follow(str(path)))
            finally:
                _SLOTS.release()

        try:
            thread = threading.Thread(target=work, daemon=True)
            thread.start()
        except RuntimeError:
            _SLOTS.release()
            return _ROOT
        thread.join(min(self._timeout, max(self._deadline - self._clock(), 0.0)))
        if self._clock() >= self._deadline:
            raise Unjudged
        return PurePosixPath(found[0]) if found else _ROOT


def local_resolver(
    roots: Sequence[PurePosixPath],
    timeout: float = RESOLVE_TIMEOUT_S,
    deadline_s: float = SCAN_DEADLINE_S,
    clock: Callable[[], float] = time.monotonic,
    follow: Callable[[str], str] | None = None,
) -> LocalResolver:
    """A resolver for one scan that follows links only below `roots`.

    A path outside every root is returned as written (a link there is not the config's to plant).
    One that cannot be resolved, or does not resolve within `timeout`, comes back as `/`, which
    reaches every secret: the caller fails closed. Each path is resolved once per scan. After
    `deadline_s` it raises `Unjudged`, so a scan that cannot finish says so. Blocking: call it from
    a worker thread. A resolution that hangs on a dead mount is abandoned in a daemon thread that
    keeps its slot (at most `RESOLVE_WORKERS` run at once in the process, whichever resolver
    started them; with none free the answer is `/`).
    """
    return LocalResolver(roots, timeout, deadline_s, clock, follow)
