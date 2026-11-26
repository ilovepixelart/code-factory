"""The configured permission reviewer: a command asked about a request before the owner."""

import asyncio
import contextlib
import os
import signal
from pathlib import Path

from code_factory.platform.contained import BASE_VARIABLES
from code_factory.platform.process import SHELL, signal_group

TIME_S = 60.0
OUTPUT_BYTES = 4096
CHUNK = 64 * 1024
REAP_S = 5.0
EMPTY_PATH = "/var/empty"


def _environment() -> dict[str, str]:
    # The base variables only: the reviewer runs outside srt and sees none of the board's secrets.
    values = {name: os.environ[name] for name in BASE_VARIABLES if name in os.environ}
    values.setdefault("PATH", EMPTY_PATH)
    return values


async def _converse(process: asyncio.subprocess.Process, request: str) -> bytes:
    assert process.stdin is not None  # noqa: S101  # PIPE was asked for
    assert process.stdout is not None  # noqa: S101
    process.stdin.write(f"{request}\n".encode())
    with contextlib.suppress(ConnectionError):
        await process.stdin.drain()
    process.stdin.close()
    first, _ = await asyncio.gather(_first_bytes(process.stdout), process.wait())
    return first


async def _first_bytes(stream: asyncio.StreamReader) -> bytes:
    """The first `OUTPUT_BYTES` of the stream; the rest is dropped so the child never blocks."""
    kept = b""
    while chunk := await stream.read(CHUNK):
        kept += chunk[: OUTPUT_BYTES - len(kept)]
    return kept


async def ask_reviewer(
    command: str, cwd: Path, request: str, time_s: float = TIME_S
) -> tuple[bool, str] | None:
    """Run `command` with `sh -c` in `cwd`, `request` on its stdin.

    Whether it exited 0 and the first 4 KiB of its output; `None` when it could not start or did
    not end within `time_s`. Its whole group is killed at the end: none outlives the answer.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            SHELL,
            "-c",
            command,
            cwd=cwd,
            env=_environment(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return None
    out: bytes | None = None
    try:
        async with asyncio.timeout(time_s):
            out = await _converse(process, request)
    except TimeoutError:
        out = None
    finally:
        signal_group(process.pid, signal.SIGKILL)
        async with asyncio.timeout(REAP_S):
            await process.wait()
    return None if out is None else (process.returncode == 0, out.decode(errors="replace"))
