"""The processes of agent runs: spawned in their own group, signalled only when provably ours.

A run outlives a board restart by design. This process signals a run's group only when it started
the process and still holds it, or when `ps` shows the process the board recorded: it started
within two seconds of the recorded start, its command line names the run's exit file, and it leads
its own group. A pid is never signalled without those facts, so a recycled pid, a process nobody
started and pids 0 and 1 (which reach every process of the user) are left alone.

`asyncio` kills a child whose transport is closed, so nothing here ever closes one; letting go of
a reference (`detach_all`) does not kill it.
"""

import asyncio
import contextlib
import gc
import os
import signal
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import anyio
import anyio.to_thread

from code_factory.platform.errors import UnavailableError
from code_factory.platform.process import signal_group
from code_factory.runs.adapters.ps import Ps
from code_factory.runs.rules import process as rules

SPAWN_TIMEOUT_S = 10.0
TERM_GRACE_S = 3.0
POLL_S = 0.05
REAP_TIMEOUT_S = 5.0
LOG_MODE = 0o600
_files = anyio.CapacityLimiter(4)


@dataclass(frozen=True)
class Target:
    """The process of a recorded run: its pid, when it started, and its exit file."""

    pid: int
    started_at: datetime | None
    exit_file: Path


@dataclass(frozen=True)
class Spawned:
    """A process just started: its pid and the start time `ps` reads for it."""

    pid: int
    started_at: datetime | None


def _open_log(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    return os.open(path, flags, LOG_MODE)


class ProcessRegistry:
    """Owns every process this board process spawned, by pid."""

    def __init__(self, ps: Ps | None = None, *, term_grace_s: float = TERM_GRACE_S) -> None:
        self._ps = ps or Ps()
        self._grace = term_grace_s
        self._held: dict[int, asyncio.subprocess.Process] = {}
        self._retired: set[int] = set()  # held pids whose group was ended: never signalled again
        self._watchers: set[asyncio.Task[int]] = set()

    def pids(self) -> list[int]:
        """The pids this process holds."""
        return list(self._held)

    def returncode(self, pid: int) -> int | None:
        """The return code of a held process that exited; `None` for one running or not held."""
        process = self._held.get(pid)
        return None if process is None else process.returncode

    async def spawn(
        self, argv: Sequence[str], *, env: Mapping[str, str], cwd: Path, log: Path
    ) -> Spawned:
        """Start `argv` in a group of its own, its output in the new file `log`.

        `FileExistsError` when `log` exists (a link is never followed); `UnavailableError` when the
        program cannot start or does not start in time.
        """
        fd = await anyio.to_thread.run_sync(_open_log, log, limiter=_files)
        try:
            async with asyncio.timeout(SPAWN_TIMEOUT_S):
                process = await asyncio.create_subprocess_exec(
                    *argv,
                    env=dict(env),
                    cwd=cwd,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=fd,
                    stderr=fd,
                    start_new_session=True,
                )
        except OSError as error:
            msg = (
                f"cannot start {argv[0]}: {getattr(error, 'strerror', None) or 'it did not start'}"
            )
            raise UnavailableError(msg) from error
        finally:
            os.close(fd)
        self._held[process.pid] = process
        self._retired.discard(process.pid)
        watcher = asyncio.create_task(process.wait())
        self._watchers.add(watcher)
        watcher.add_done_callback(self._watchers.discard)
        try:
            started = await self._ps.start_time(process.pid)
        except BaseException:
            # The caller never gets the handle, so it could not end the child: this does.
            with anyio.CancelScope(shield=True):
                signal_group(process.pid, signal.SIGKILL)
                with contextlib.suppress(TimeoutError):
                    await self._reap(process.pid)
            raise
        return Spawned(
            pid=process.pid,
            started_at=None if started is None else datetime.fromtimestamp(started, UTC),
        )

    async def _verified(self, target: Target) -> bool:
        if rules.signal_group(target.pid) is None or target.pid in self._retired:
            return False
        held = self._held.get(target.pid)
        if held is not None:
            return held.returncode is None  # a reaped pid is free for another group to take
        return await self._recorded(target)

    async def _recorded(self, target: Target) -> bool:
        """Whether `ps` shows the process the board recorded, leading its own group."""
        if target.started_at is None:
            return False
        started = await self._ps.start_time(target.pid)
        command = await self._ps.command(target.pid)
        if not rules.same_process(
            started, target.started_at.timestamp(), command or "", target.exit_file.name
        ):
            return False
        try:
            return os.getpgid(target.pid) == target.pid
        except ProcessLookupError:
            return False

    async def alive(self, target: Target) -> bool:
        """Whether the run's process still runs: held and not exited, or verified by `ps`."""
        process = self._held.get(target.pid)
        if process is not None:
            return process.returncode is None
        return await self._verified(target)

    async def send_signal(self, target: Target, sig: signal.Signals) -> bool:
        """Signal the run's group; `False`, with nothing sent, unless the process is ours."""
        if not await self._verified(target):
            return False
        signal_group(target.pid, sig)
        return True

    async def stop(self, target: Target) -> None:
        """SIGTERM the group, wait up to the grace, then SIGKILL; a held process is reaped."""
        if not await self.send_signal(target, signal.SIGTERM):
            return
        try:
            async with asyncio.timeout(self._grace):
                # An adopted process has no event to wait on, only `ps`.
                while await self.alive(target):  # noqa: ASYNC110
                    await asyncio.sleep(POLL_S)
        except TimeoutError:
            await self.send_signal(target, signal.SIGKILL)
        await self._reap(target.pid)

    async def kill(self, target: Target) -> bool:
        """SIGKILL the group and reap a held process; `False`, with nothing sent, unless ours."""
        sent = await self.send_signal(target, signal.SIGKILL)
        if sent:
            await self._reap(target.pid)
        return sent

    def end_leftovers(self, target: Target) -> None:
        """SIGKILL what remains of a held run's group after its leader ended.

        The leader's exit does not free its group's id while members remain, so the held pid is
        signalled even though it was reaped; it is then retired and never signalled again.
        """
        if target.pid not in self._held or target.pid in self._retired:
            return
        if rules.signal_group(target.pid) is not None:
            signal_group(target.pid, signal.SIGKILL)
        self._retired.add(target.pid)

    async def _reap(self, pid: int) -> None:
        process = self._held.get(pid)
        if process is not None:
            async with asyncio.timeout(REAP_TIMEOUT_S):
                await process.wait()

    async def reap_all(self) -> None:
        """Wait for every held process to exit."""
        for pid in self.pids():
            with contextlib.suppress(TimeoutError):
                await self._reap(pid)

    def detach_all(self) -> None:
        """Let go of every held process without signalling it: runs outlive a board restart."""
        for watcher in list(self._watchers):
            watcher.cancel()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)  # one per transport let go of
            self._held.clear()
            gc.collect()
