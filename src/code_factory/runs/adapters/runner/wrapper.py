"""Start the agent, redact and copy its output, record its exit."""

import asyncio
import json
import os
import re
import signal
import sys
from collections.abc import Sequence
from pathlib import Path

from code_factory.runs.models import TIMEOUT_CODE
from code_factory.runs.rules.process import wrapper_status
from code_factory.runs.rules.stream import OutputRedaction

USAGE = "usage: runner <exit file> [--timeout-seconds <seconds>] -- <command> [args...]"
CONTEXT_VARIABLE = "CODE_FACTORY_OWNER_CONTEXT"
NOT_FOUND = 127
CHUNK = 64 * 1024
USAGE_STATUS = 2
# What the board names an exit file: a run id (`secrets.token_hex(6)`) and `.exit`.
_EXIT_NAME = re.compile(r"[0-9a-f]{12}\.exit")
_stop_requested = False


def _request_stop(_number: int, _frame: object) -> None:
    global _stop_requested  # noqa: PLW0603  # set by a signal handler, read once before the start
    _stop_requested = True


def _say(text: str) -> None:
    sys.stdout.buffer.write(text.encode() + b"\n")
    sys.stdout.buffer.flush()


def find_program(name: str, search: str) -> str | None:
    """`name` as a file this user may run in an absolute folder of `search`; a path is kept."""
    if "/" in name:
        return name if os.access(name, os.X_OK) else None
    for folder in search.split(os.pathsep):
        candidate = Path(folder) / name
        if Path(folder).is_absolute() and candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def load_redaction(reference: str | None) -> OutputRedaction | None:
    """The redaction of the patterns file the board named; `None` when none is named.

    The file holds `{"patterns": [[text, stand-in], ...]}`. Raises `OSError` or `ValueError` when
    it cannot be read: a run that cannot be redacted does not start.
    """
    if reference is None or reference == "":
        return None
    said = json.loads(Path(reference).read_text())
    return OutputRedaction([(str(found), str(stand_in)) for found, stand_in in said["patterns"]])


def exit_file(text: str) -> Path | None:
    """The exit file `text` names, or None unless it is absolute, has no `..` and is a run's."""
    path = Path(text)
    if not path.is_absolute() or ".." in path.parts or _EXIT_NAME.fullmatch(path.name) is None:
        return None
    return path


def record_exit(path: Path, code: int) -> None:
    """Write the exit code with an atomic rename, so a reader sees all of it or none."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    temporary.write_text(f"{code}\n")
    temporary.replace(path)


async def _copy(reader: asyncio.StreamReader, stream: OutputRedaction | None) -> None:
    while chunk := await reader.read(CHUNK):
        data = chunk if stream is None else stream.push(chunk)
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    if stream is not None:
        sys.stdout.buffer.write(stream.finish())
        sys.stdout.buffer.flush()


async def run(exit_file: Path, command: Sequence[str], timeout_s: int | None = None) -> int:
    """Run `command`; the agent's exit code, recorded in `exit_file` first."""
    code = await _run(command, timeout_s)
    try:
        record_exit(exit_file, code)
        if code == TIMEOUT_CODE:
            _say(f"the run exceeded its time limit of {timeout_s} seconds")
    finally:
        if code == TIMEOUT_CODE:
            # The wrapper owns this group. End descendants even when the board is offline.
            os.killpg(os.getpid(), signal.SIGKILL)
    return code


async def _run(command: Sequence[str], timeout_s: int | None) -> int:
    try:
        stream = load_redaction(os.environ.get(CONTEXT_VARIABLE))
    except (OSError, ValueError, KeyError, TypeError) as error:
        _say(f"the owner context to redact could not be read ({error}); the run did not start")
        return 1
    program = find_program(command[0], os.environ.get("PATH", ""))
    if program is None:
        _say(f"{command[0]}: not found in the absolute folders of PATH")
        return NOT_FOUND
    if _stop_requested:
        return -signal.SIGTERM
    process = await asyncio.create_subprocess_exec(
        program,
        *command[1:],
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdout is not None  # noqa: S101  # PIPE was asked for
    try:
        async with asyncio.timeout(timeout_s):
            await asyncio.gather(_copy(process.stdout, stream), process.wait())
    except TimeoutError:
        return TIMEOUT_CODE
    except BaseException:
        # The wrapper is what supervises the agent: it never ends with the agent still running.
        if process.returncode is None:
            process.kill()
        await asyncio.shield(process.wait())
        raise
    return process.returncode if process.returncode is not None else 1


def main(argv: Sequence[str]) -> int:
    """The wrapper's exit status: the agent's, as `128 - code` for a signal death."""
    timeout_s = None
    if len(argv) >= 5 and argv[1] == "--timeout-seconds":  # noqa: PLR2004  # five required words
        try:
            timeout_s = int(argv[2])
        except ValueError:
            timeout_s = 0
        argv = [argv[0], *argv[3:]]
    if len(argv) < 3 or argv[1] != "--" or timeout_s == 0:  # noqa: PLR2004  # three required words
        sys.stderr.write(USAGE + "\n")
        return USAGE_STATUS
    if timeout_s is not None and (timeout_s < 0 or os.getpgrp() != os.getpid()):
        sys.stderr.write("a run deadline requires positive seconds and its own process group\n")
        return USAGE_STATUS
    recorded = exit_file(argv[0])
    if recorded is None:
        sys.stderr.write(
            "the exit file must be an absolute path ending in <12 hex digits>.exit, "
            f"not {argv[0]}\n"
        )
        return USAGE_STATUS
    signal.signal(signal.SIGTERM, _request_stop)  # a handler: an ignored signal survives exec
    return wrapper_status(asyncio.run(run(recorded, argv[2:], timeout_s)))
