"""Facts about a run's process: which group may be signalled, which process is the recorded one."""

import re

MAX_PID = 2**31 - 1
START_TOLERANCE_S = 2.0  # `ps` reports the start to the second
_ETIME = re.compile(r"^(?:(?:(\d+)-)?(\d+):)?(\d+):(\d+)$")
_SIGNAL_BASE = 128


def signal_group(pid: int) -> int | None:
    """`pid` when its group may be signalled, else `None`.

    1 and below reach every process of the user or the caller's own group; past 2**31 - 1 is no
    pid at all.
    """
    return pid if 1 < pid <= MAX_PID else None


def elapsed_seconds(etime: str) -> int | None:
    """`[[dd-]hh:]mm:ss` of `ps -o etime` in seconds; `None` for anything else."""
    found = _ETIME.fullmatch(etime.strip())
    if found is None:
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in found.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def same_process(
    ps_start: float | None, recorded: float, command: str, exit_file_name: str
) -> bool:
    """Whether the process `ps` shows is the one a board recorded.

    It started within two seconds of the recorded start and its command line names the run's exit
    file. A recycled pid fails the first, an unrelated process the second.
    """
    if ps_start is None:
        return False
    return abs(ps_start - recorded) <= START_TOLERANCE_S and exit_file_name in command


def exit_status(returncode: int) -> int:
    """The exit code a run records: asyncio's own, negative for a signal."""
    return returncode


def wrapper_status(code: int) -> int:
    """The wrapper's own exit status for the agent's `code`: a signal `n` is `128 + n`."""
    return _SIGNAL_BASE - code if code < 0 else code
