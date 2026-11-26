"""What `ps` says of a process: when it started and its command line."""

import asyncio
from datetime import UTC, datetime

from code_factory.platform.process import run_process

PS = "/bin/ps"  # by its path: a PATH folder a run wrote must not supply it
TIMEOUT_S = 5.0
OUTPUT_CAP = 64 * 1024
ENV = {"TZ": "UTC", "LC_ALL": "C"}
_LSTART = "%a %b %d %H:%M:%S %Y"


def parse_start(text: str) -> float | None:
    """Epoch seconds of `ps -o lstart=` output (UTC, one second resolution); `None` for junk."""
    try:
        return datetime.strptime(text.strip(), _LSTART).replace(tzinfo=UTC).timestamp()
    except ValueError:
        return None


class Ps:
    """Reads a process by pid; at most eight `ps` run at once."""

    def __init__(self, program: str = PS) -> None:
        self._program = program
        self._at_once = asyncio.Semaphore(8)

    async def _field(self, field: str, pid: int) -> str | None:
        async with self._at_once:
            done = await run_process(
                [self._program, "-o", f"{field}=", "-p", str(pid)],
                env=ENV,
                timeout_s=TIMEOUT_S,
                output_cap=OUTPUT_CAP,
            )
        if done.code != 0 or done.truncated or done.timed_out:
            return None
        text = done.stdout.decode(errors="replace").strip()
        return text or None

    async def start_time(self, pid: int) -> float | None:
        """When the process started in epoch seconds; `None` when it is gone."""
        text = await self._field("lstart", pid)
        return None if text is None else parse_start(text)

    async def command(self, pid: int) -> str | None:
        """The process's command line; `None` when it is gone."""
        return await self._field("command", pid)
