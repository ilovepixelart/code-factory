"""The gate's heavy-step lock as the board holds it around a checks container's run.

A symbolic link in `<state>-locks` whose target names its holder, made by `symlink`, which makes
it with its holder or fails. It speaks the protocol of a repository's own gate script; the board
takes it only for a container run, where the gate inside the container cannot.
"""

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import anyio
import anyio.to_thread

from code_factory.checks.rules import counts_as_holder, holder_name, holder_pid, next_move
from code_factory.platform.errors import UnavailableError
from code_factory.platform.process import run_process

POLL_S = 0.25
PS_TIMEOUT_S = 5.0
PS = "/bin/ps"
_files = anyio.CapacityLimiter(2)

Say = Callable[[str], Awaitable[None]]
Kill = Callable[[int, int], None]


def process_runs(pid: int, kill: Kill = os.kill) -> bool:
    """Whether process `pid` runs.

    Never probed unless above 1: a signal to 0 or 1 reaches whole process groups or every process
    of the user. Gone only when the system says there is no such process.
    """
    if pid <= 1:
        return False
    try:
        kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _make(link: Path, text: str) -> tuple[bool, str | None]:
    """Make the link: made, or what holds it, or `(False, None)` when it cannot be made."""
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False, None
    try:
        link.symlink_to(text)
    except FileExistsError:
        if link.exists(follow_symlinks=False) and not link.is_symlink():
            return False, None  # not a lock at all: nothing to wait for
        return False, _read(link) or ""
    except OSError:
        return False, None
    return True, text


def _read(link: Path) -> str | None:
    try:
        return str(link.readlink())
    except OSError:
        return None


def _release(link: Path, text: str) -> None:
    if _read(link) == text:
        link.unlink(missing_ok=True)


async def _command_of(pid: int) -> str | None:
    try:
        done = await run_process([PS, "-p", str(pid), "-o", "command="], timeout_s=PS_TIMEOUT_S)
    except UnavailableError:
        return None
    text = done.stdout.decode(errors="replace").strip()
    return text or None


class HeavyHold:
    """The lock while held; empty when the board went on without it."""

    def __init__(self, link: Path, mine: str | None) -> None:
        self._link = link
        self._mine = mine

    @property
    def held(self) -> bool:
        """Whether this holds the lock."""
        return self._mine is not None

    async def release(self) -> None:
        """Remove the link, only when it is still ours."""
        if self._mine is not None:
            await anyio.to_thread.run_sync(_release, self._link, self._mine, limiter=_files)


class HeavyLockFile:
    """The lock file `link`."""

    def __init__(self, link: Path, *, kill: Kill = os.kill) -> None:
        self._link = link
        self._kill = kill

    async def holder(self) -> str | None:
        """The text the lock holds now: `<pid> <step> in <tree> on <branch>`; None when free."""
        return await anyio.to_thread.run_sync(_read, self._link, limiter=_files)

    async def take(self, text: str, bound: float, say: Say) -> HeavyHold:
        """Take the lock for `text`, waiting for its holder as a gate does.

        A holder that is gone, or counts as none, is released; after `bound` seconds in all the
        board goes on without the lock, and the hold is empty. `say` is told, as a gate's line
        without its lead, each holder waited for once and why it went on.
        """
        asked = time.monotonic()
        seen = ""
        while True:
            made, held = await anyio.to_thread.run_sync(_make, self._link, text, limiter=_files)
            if made:
                return HeavyHold(self._link, text)
            if held is None:
                return HeavyHold(self._link, None)
            if not held:
                continue
            pid = holder_pid(held)
            running = pid is not None and process_runs(pid, self._kill)
            command = await _command_of(pid) if pid is not None and running else None
            counts = running and counts_as_holder(held, command)
            move = next_move(
                held, running=running, counts=counts, waited=time.monotonic() - asked, bound=bound
            )
            if move.kind == "release":
                await anyio.to_thread.run_sync(_release, self._link, held, limiter=_files)
            elif move.kind == "go_on":
                await say(move.why)
                return HeavyHold(self._link, None)
            else:
                if held != seen:
                    await say(f"waits for the heavy-step lock, held by {holder_name(held)}")
                    seen = held
                await asyncio.sleep(POLL_S)
