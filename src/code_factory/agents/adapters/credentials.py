"""Provider keys in the operating system's credential store, read at the moment of use.

macOS keeps them with `security`, Linux with `secret-tool`, under the service `code-factory`;
the process environment of the same name is the fallback. A value is never cached, logged,
raised in an error or passed on a command line.
"""

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Protocol

from pydantic import SecretStr

from code_factory.platform.errors import BadRequestError, UnavailableError
from code_factory.platform.process import run_process
from code_factory.platform.programs import find_program

SERVICE = "code-factory"
READ_TIMEOUT_S = 5.0
STORE_TIMEOUT_S = 600.0
KEY_NAME = re.compile(r"[A-Z0-9_]+")
_MACOS = sys.platform == "darwin"
_PROGRAM = "security" if _MACOS else "secret-tool"


def _check_name(name: str) -> None:
    """Refuse a name that is not capitals, digits and `_`, so it is never read as an option."""
    if KEY_NAME.fullmatch(name) is None:
        msg = "a key name is capitals, digits and _"
        raise BadRequestError(msg)


def _arguments(action: str, name: str) -> list[str]:
    if _MACOS:
        verbs = {
            "read": ["find-generic-password", "-s", SERVICE, "-a", name, "-w"],
            "remove": ["delete-generic-password", "-s", SERVICE, "-a", name],
            "store": ["add-generic-password", "-U", "-s", SERVICE, "-a", name, "-w"],
        }
    else:
        verbs = {
            "read": ["lookup", "service", SERVICE, "account", name],
            "remove": ["clear", "service", SERVICE, "account", name],
            "store": ["store", "--label", f"{SERVICE} {name}", "service", SERVICE, "account", name],
        }
    return verbs[action]


async def _end(process: asyncio.subprocess.Process) -> None:
    """Terminate `process`, kill it after a short grace, and always reap it."""
    if process.returncode is None:
        process.terminate()
    try:
        async with asyncio.timeout(1.0):
            await process.wait()
    except TimeoutError:
        process.kill()
        await process.wait()


class KeyStore(Protocol):
    """What the service needs of a credential store; tests give it a fake."""

    async def read(self, name: str) -> SecretStr | None:
        """The key `name`, if set."""
        ...

    async def has(self, name: str) -> bool:
        """Whether the key is set."""
        ...

    async def remove(self, name: str) -> bool:
        """Remove the key; whether it was there."""
        ...

    async def store(self, name: str) -> int:
        """Store a key by name; the exit code."""
        ...


class CredentialStore:
    """Reads, tests, stores and removes keys by name; `store` is for the command line only."""

    def __init__(
        self,
        *,
        program: Path | None = None,
        timeout_s: float = READ_TIMEOUT_S,
        store_timeout_s: float = STORE_TIMEOUT_S,
    ) -> None:
        self._program = program
        self._timeout_s = timeout_s
        self._store_timeout_s = store_timeout_s
        self._concurrency = asyncio.Semaphore(4)

    async def _found(self) -> Path | None:
        if self._program is not None:
            return self._program
        return await find_program(_PROGRAM, [])

    async def _run(self, action: str, name: str) -> tuple[int | None, bytes]:
        """The exit code (None when it did not finish or start) and stdout of one store call."""
        program = await self._found()
        if program is None:
            return None, b""
        try:
            async with self._concurrency:
                done = await run_process(
                    [str(program), *_arguments(action, name)],
                    timeout_s=self._timeout_s,
                    output_cap=64 * 1024,
                    grace_s=1.0,
                )
        except UnavailableError:
            return None, b""
        return done.code, done.stdout

    async def read(self, name: str) -> SecretStr | None:
        """The key `name`: the credential store's, else the environment variable; empty is none."""
        _check_name(name)
        code, out = await self._run("read", name)
        if code == 0:
            value = out.decode("utf-8", errors="replace").rstrip("\r\n")
            if value:
                return SecretStr(value)
        value = os.environ.get(name, "")
        return SecretStr(value) if value else None

    async def has(self, name: str) -> bool:
        """Whether a key `name` is set, in the store or the environment; never its value."""
        return await self.read(name) is not None

    async def remove(self, name: str) -> bool:
        """Remove the key from the store; whether the store did."""
        _check_name(name)
        code, _ = await self._run("remove", name)
        return code == 0

    async def store(self, name: str) -> int:
        """Store a key `name`: the program prompts on the terminal, so no value is passed here.

        Standard input and output are the caller's. Returns the program's exit code; 127 when no
        credential store program is installed.
        """
        _check_name(name)
        program = await self._found()
        if program is None:
            return 127
        # The program keeps the terminal, so it stays in the caller's process group and is ended
        # by its own pid, never by a group.
        process = await asyncio.create_subprocess_exec(program, *_arguments("store", name))
        try:
            async with asyncio.timeout(self._store_timeout_s):
                return await process.wait()
        except TimeoutError:
            await asyncio.shield(_end(process))
            return 1
        except asyncio.CancelledError:
            await asyncio.shield(_end(process))
            raise
