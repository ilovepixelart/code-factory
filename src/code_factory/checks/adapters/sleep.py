"""When the machine last slept, read the way a failure caused by sleep is told from the rest."""

from pathlib import Path

from code_factory.platform.errors import UnavailableError
from code_factory.platform.process import run_process

SYSCTL = Path("/usr/sbin/sysctl")  # by its path and with no environment: a sysctl on PATH could lie
TIMEOUT_S = 5.0


async def sleep_time() -> str | None:
    """`kern.sleeptime` as sysctl prints it; None where it cannot be read."""
    try:
        done = await run_process([str(SYSCTL), "-n", "kern.sleeptime"], env={}, timeout_s=TIMEOUT_S)
    except UnavailableError:
        return None
    return done.stdout.decode(errors="replace") if done.code == 0 else None
