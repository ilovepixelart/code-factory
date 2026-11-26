"""IO at the edge: the notes a person gives a release, from a file or standard input."""

import asyncio
import sys
from pathlib import Path

import anyio
from anyio import CapacityLimiter

from code_factory.platform.errors import BadRequestError, NotFoundError, UnavailableError

STANDARD_INPUT = "-"
MAX_BYTES = 1024 * 1024
FILE_TIMEOUT_S = 10
# Reads run in worker threads; this limiter keeps them from taking the default pool.
_FILES = CapacityLimiter(2)


def _read(source: str) -> bytes:
    if source == STANDARD_INPUT:
        return bytes(sys.stdin.buffer.read(MAX_BYTES + 1))
    try:
        with Path(source).open("rb") as handle:
            return handle.read(MAX_BYTES + 1)
    except FileNotFoundError:
        msg = f"{source}: no such file; give the notes' file, or - for standard input"
        raise NotFoundError(msg) from None
    except OSError as error:
        msg = f"{source}: cannot be read ({error.strerror})"
        raise BadRequestError(msg) from None


async def read_notes(source: str, timeout_s: float = FILE_TIMEOUT_S) -> str:
    """The text of file `source`, or of standard input for `-`: UTF-8, at most 1 MiB.

    A file read gives up after `timeout_s` (a stalled mount); standard input is a person's own
    and waits as long as they do, because a thread blocked on a pipe cannot be stopped.
    """
    if source == STANDARD_INPUT:
        data = await anyio.to_thread.run_sync(_read, source, limiter=_FILES)
    else:
        try:
            async with asyncio.timeout(timeout_s):
                data = await anyio.to_thread.run_sync(_read, source, limiter=_FILES)
        except TimeoutError:
            msg = f"{source} did not answer within {timeout_s:g} s; check the mount it is on"
            raise UnavailableError(msg) from None
    if len(data) > MAX_BYTES:
        msg = f"{source} is over 1 MiB; release notes are text, not an attachment"
        raise BadRequestError(msg)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        msg = f"{source} is not UTF-8 text"
        raise BadRequestError(msg) from None
