"""Opens a URL in the owner's default browser through the platform's opener program."""

import asyncio
import shutil
import sys

from code_factory.hooks.models import OpenerUnavailableError

OPEN_S = 10.0
_PROGRAMS = {"darwin": "open", "linux": "xdg-open"}


class BrowserOpener:
    """`open` on macOS, `xdg-open` on Linux; the URL never reaches a log."""

    def __init__(self, timeout_s: float = OPEN_S) -> None:
        self._timeout_s = timeout_s
        self._lock = asyncio.Lock()

    async def open_url(self, url: str) -> None:
        """`OpenerUnavailableError` when no program can open it or the program fails."""
        name = _PROGRAMS.get(sys.platform)
        if name is None:
            msg = f"no browser opener for {sys.platform}"
            raise OpenerUnavailableError(msg)
        program = shutil.which(name)
        if program is None:
            msg = f"{name} is not installed"
            raise OpenerUnavailableError(msg)
        async with self._lock:
            await self._run(name, program, url)

    async def _run(self, name: str, program: str, url: str) -> None:
        process = await asyncio.create_subprocess_exec(
            program,
            url,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(self._timeout_s):
                code = await process.wait()
        except TimeoutError:
            msg = f"{name} did not return within {self._timeout_s:g} seconds"
            raise OpenerUnavailableError(msg) from None
        finally:
            if process.returncode is None:
                process.kill()
                await asyncio.shield(process.wait())
        if code != 0:
            msg = f"{name} exited with {code}"
            raise OpenerUnavailableError(msg)
