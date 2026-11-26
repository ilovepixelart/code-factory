"""Run one subprocess with a time limit, a cap on what it may print, and a guaranteed reaping.

The one place that starts a short-lived child for git, stages and the like. The child gets its own
session, so a limit, a cap or a cancellation stops everything it started: SIGTERM to the group, a
grace period, then SIGKILL, and the child is always waited for. A signal goes only to a group this
module started (a process group id above 1: `kill(-1)` and `killpg(1)` reach every process the
user owns).

A caller that runs many at once bounds them with its own semaphore.
"""

import asyncio
import contextlib
import os
import signal
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import anyio
import anyio.to_thread

from code_factory.platform.errors import UnavailableError

MIB = 1024 * 1024
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_OUTPUT_CAP = 8 * MIB
DEFAULT_GRACE_S = 3.0
SIGHUP_CODE = 128 + signal.SIGHUP
_CHUNK = 64 * 1024
SHELL = "/bin/sh"  # by its path: a PATH folder a run wrote must not supply the shell
_log_files = anyio.CapacityLimiter(4)


@dataclass(frozen=True)
class ProcessResult:
    """What a run produced. `code` is None when the limit or the cap stopped the child."""

    code: int | None
    stdout: bytes
    stderr: bytes
    truncated: bool = False
    timed_out: bool = False


def checked_group(pgid: int) -> int:
    """`pgid` when it may be signalled.

    1 and below reach every process of the user, or the caller's own group.

    Pure, so a test proves the refusal without a signal that would be unsafe if the guard failed.
    """
    if pgid <= 1:
        msg = f"refusing to signal process group {pgid}"
        raise ValueError(msg)
    return pgid


def signal_group(pgid: int, sig: signal.Signals) -> None:
    """Send `sig` to the process group `pgid`; a group already gone is not an error.

    macOS answers "not permitted" for a group that holds only zombies, which is the same thing.
    """
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(checked_group(pgid), sig)


async def stop_group(
    process: asyncio.subprocess.Process, grace_s: float, *, interrupted: bool = True
) -> None:
    """Wait for `process`; when `interrupted`, first end its group: SIGTERM, `grace_s`, SIGKILL.

    The group is signalled even after its leader exited (a worker may outlive it), and SIGKILL
    follows the grace period whatever the leader did. No process id equal to a live group's can be
    handed out, and an empty group answers "no such process".
    """
    if interrupted:
        signal_group(process.pid, signal.SIGTERM)
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(grace_s):
                await process.wait()
        signal_group(process.pid, signal.SIGKILL)
    async with asyncio.timeout(grace_s + 5):
        await process.wait()


class _Capture:
    """What one stream has delivered so far; it survives the reader being cancelled."""

    def __init__(self, cap: int, hit: asyncio.Event) -> None:
        self.kept = bytearray()
        self.cut = False
        self._cap = cap
        self._hit = hit

    async def read(self, stream: asyncio.StreamReader) -> None:
        """Keep up to the cap; on more, mark the cut and wake the caller, then drain to the end.

        Reading on to the end (discarding) lets the pipe close once the child is stopped.
        """
        while chunk := await stream.read(_CHUNK):
            room = self._cap - len(self.kept)
            self.kept += chunk[:room]
            if len(chunk) > room:
                self.cut = True
                self._hit.set()


async def _until_done(
    process: asyncio.subprocess.Process, readers: list[asyncio.Task[None]]
) -> None:
    await process.wait()
    await asyncio.gather(*readers)


async def run_process(  # noqa: PLR0913  # the limits of one run, all optional
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    output_cap: int = DEFAULT_OUTPUT_CAP,
    grace_s: float = DEFAULT_GRACE_S,
) -> ProcessResult:
    """Run `argv` (never a shell string) and return its code and what it printed.

    `env` replaces the environment when given. Each stream keeps at most `output_cap` bytes; when
    more was coming the child is stopped and `truncated` is set. Past `timeout_s` the child is
    stopped and `timed_out` is set. A program that cannot start raises `UnavailableError`.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=None if env is None else dict(env),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    except FileNotFoundError:
        msg = f"cannot start {argv[0]}: no such file"
        raise UnavailableError(msg) from None
    except PermissionError:
        msg = f"cannot start {argv[0]}: permission denied"
        raise UnavailableError(msg) from None
    assert process.stdout is not None  # noqa: S101  # PIPE was asked for
    assert process.stderr is not None  # noqa: S101
    hit = asyncio.Event()
    out, err = _Capture(output_cap, hit), _Capture(output_cap, hit)
    readers = [
        asyncio.create_task(out.read(process.stdout)),
        asyncio.create_task(err.read(process.stderr)),
    ]
    done = asyncio.create_task(_until_done(process, readers))
    capped = asyncio.create_task(hit.wait())
    timed_out = False
    try:
        async with asyncio.timeout(timeout_s):
            await asyncio.wait({done, capped}, return_when=asyncio.FIRST_COMPLETED)
    except TimeoutError:
        timed_out = True
    finally:
        await _finish(process, grace_s)
        capped.cancel()
        # The group is dead, so the pipes reach their end; a reader still waiting is cancelled.
        await asyncio.wait({done, *readers}, timeout=grace_s)
        for task in (done, *readers):
            task.cancel()
        await asyncio.gather(done, capped, *readers, return_exceptions=True)
    truncated = out.cut or err.cut
    code = None if truncated or timed_out else process.returncode
    return ProcessResult(
        code, bytes(out.kept), bytes(err.kept), truncated=truncated, timed_out=timed_out
    )


async def _finish(process: asyncio.subprocess.Process, grace_s: float) -> None:
    """End the child's group and reap it, even while the caller is being cancelled.

    Always signalled: a leader that exited on its own may have left workers running.
    """
    await asyncio.shield(stop_group(process, grace_s))


def _open_log(log: Path) -> IO[bytes]:
    log.parent.mkdir(parents=True, exist_ok=True)
    return log.open("wb")


def _code(returncode: int | None) -> int | None:
    # -1 is the contained runner's "could not be contained"; a hang-up death reads as the shell's.
    return SIGHUP_CODE if returncode == -signal.SIGHUP else returncode


async def run_logged(
    command: str,
    *,
    cwd: Path,
    log: Path,
    env: Mapping[str, str],
    limit_s: float | None = None,
) -> int | None:
    """Run the shell line `command` in `cwd`, its output (both streams) in the file `log`.

    The output goes to the file, not through a pipe, so output of any size never sits in memory.
    Returns the exit code (a signal death is the negative signal number, except SIGHUP: 129), or
    None when `limit_s` ran out and the group was stopped. The child's environment is exactly
    `env`.
    """
    sink = await anyio.to_thread.run_sync(_open_log, log, limiter=_log_files)
    try:
        process = await asyncio.create_subprocess_exec(
            SHELL,
            "-c",
            command,
            cwd=cwd,
            env=dict(env),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=sink,
            stderr=sink,
            start_new_session=True,
        )
        try:
            async with asyncio.timeout(limit_s):
                await process.wait()
        except TimeoutError:
            return None
        finally:
            await _finish(process, DEFAULT_GRACE_S)
        return _code(process.returncode)
    finally:
        sink.close()
