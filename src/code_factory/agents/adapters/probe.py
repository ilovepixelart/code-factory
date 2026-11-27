"""Asking model servers: their model lists, the local servers on this machine, and a model check.

No proxy variable, cookie, redirect or HTTP/2 is used, so a request goes only to the address the
rules allow and a key reaches only the host its kind is for. The key travels in headers only.
"""

import asyncio
import errno
import hashlib
import os
import re
from pathlib import Path
from time import monotonic
from typing import Any

import httpx
from pydantic import SecretStr

from code_factory.agents.models.connections import ConnectionDefinition, Found, Silence, Status
from code_factory.agents.rules.connections import KINDS, models_address, rules
from code_factory.agents.rules.login import CodexLogin, catalog_models
from code_factory.agents.rules.model_checks import Request
from code_factory.agents.rules.probes import (
    LOCAL_PROBES,
    key_headers,
    loaded_address,
    local_state,
    models,
    with_loaded,
)
from code_factory.platform.errors import BadRequestError, UnavailableError
from code_factory.platform.process import run_process
from code_factory.platform.programs import find_program

PROBE_S = 3.0
CONNECT_S = 2.0
CHECK_S = 60.0
BODY_CAP = 4 * 1024 * 1024
Answer = tuple[int, str] | Silence
HTTP_OK = 200
CODEX_MODELS_URL = "https://chatgpt.com/backend-api/codex/models"
CODEX_CACHE_S = 120
CODEX_VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?")


async def codex_version() -> str:
    """The installed CLI version sent to the Codex catalog."""
    excluded = (Path.cwd(),)
    binary = await find_program("codex", excluded)
    if binary is None:
        return ""
    node = await find_program("node", excluded)  # npm installs Codex with a Node entry point
    search = os.defpath if node is None else os.pathsep.join((str(node.parent), os.defpath))
    try:
        result = await run_process(
            (str(binary), "--version"), env={"PATH": search}, timeout_s=3, output_cap=1024
        )
    except UnavailableError:
        return ""
    version = result.stdout.decode("ascii", errors="replace").strip().removeprefix("codex-cli ")
    return version if result.code == 0 and CODEX_VERSION.fullmatch(version) is not None else ""


def _refused(error: BaseException | None) -> bool:
    """Whether a closed port is in the cause chain of `error`."""
    seen = 0
    while error is not None and seen < 8:  # noqa: PLR2004  # a chain is short; a cycle is not followed
        if isinstance(error, OSError) and error.errno == errno.ECONNREFUSED:
            return True
        error = error.__cause__ or error.__context__
        seen += 1
    return False


async def _read(response: httpx.Response) -> str:
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body += chunk[: BODY_CAP - len(body)]
        if len(body) >= BODY_CAP:
            break
    return body.decode("utf-8", errors="replace")


class ModelProbe:
    """Asks model servers; every request has a total time limit of its own."""

    def __init__(
        self, *, probe_s: float = PROBE_S, check_s: float = CHECK_S, connect_s: float = CONNECT_S
    ) -> None:
        self._probe_s = probe_s
        self._check_s = check_s
        self._connect_s = connect_s
        self._probes = asyncio.Semaphore(8)
        self._codex_lock = asyncio.Lock()
        self._codex_cached: tuple[tuple[str, bytes], float, Status] | None = None

    def _client(self, seconds: float) -> httpx.AsyncClient:
        timeout = httpx.Timeout(seconds, connect=min(self._connect_s, seconds))
        return httpx.AsyncClient(
            trust_env=False, follow_redirects=False, http2=False, timeout=timeout, cookies=None
        )

    async def _send(
        self,
        method: str,
        address: str,
        headers: dict[str, str],
        body: dict[str, Any] | None,
        seconds: float,
    ) -> Answer:
        try:
            async with (
                asyncio.timeout(seconds),
                self._client(seconds) as client,
                client.stream(method, address, headers=headers, json=body) as response,
            ):
                return response.status_code, await _read(response)
        except httpx.TransportError as error:
            return Silence.REFUSED if _refused(error) else Silence.NO_ANSWER
        except TimeoutError, httpx.InvalidURL, httpx.RequestError:
            return Silence.NO_ANSWER

    async def get(self, address: str, headers: dict[str, str]) -> Answer:
        """`GET address`: the status and body, or why none came back."""
        async with self._probes:
            return await self._send("GET", address, headers, None, self._probe_s)

    async def ask(self, request: Request) -> Answer:
        """Send one request of a model check: the status and body, or why none came back."""
        headers = {
            name: value for name, _, value in (line.partition(": ") for line in request.headers)
        }
        return await self._send("POST", request.address, headers, request.body, self._check_s)

    async def status(self, connection: ConnectionDefinition, key: SecretStr | None) -> Status:
        """Whether `connection` answers `GET <address>/v1/models`, and its models, or why not.

        Nothing is sent while a key variable it needs holds no value, or when it breaks the rules.
        """
        try:
            rules(connection)
            address = models_address(connection)
            where = loaded_address(connection)
        except BadRequestError as why:
            return Status(name=connection.name, answers=False, problem=str(why))
        if connection.key_env and (key is None or not key.get_secret_value()):
            return Status(
                name=connection.name, answers=False, problem=f"{connection.key_env} is not set"
            )
        headers = key_headers(connection, key if connection.key_env else None)
        body, problem = await self._body(address, headers)
        listed = models(body)
        if where is not None and not problem:
            loaded, problem = await self._body(where, headers)
            listed = with_loaded(connection.kind, listed, loaded)
        if problem:
            return Status(name=connection.name, answers=False, problem=problem)
        return Status(name=connection.name, answers=True, models=listed)

    async def codex_status(self, connection: str, login: CodexLogin) -> Status:
        """Read the account's model catalog without starting a model turn."""
        token = login.access_token.get_secret_value()
        identity = (login.account_id, hashlib.sha256(token.encode()).digest())
        async with self._codex_lock:
            cached = self._codex_cached
            if cached and cached[0] == identity and cached[1] > monotonic():
                return cached[2].model_copy(update={"name": connection})
            status = await self._codex_status(connection, token, login.account_id)
            if status.answers:
                self._codex_cached = (identity, monotonic() + CODEX_CACHE_S, status)
            return status

    async def _codex_status(self, name: str, token: str, account: str) -> Status:
        version = await codex_version()
        if not version:
            problem = "the Codex CLI version could not be read; install or update the Codex CLI"
            return Status(name=name, answers=False, problem=problem)
        body, problem = await self._body(
            f"{CODEX_MODELS_URL}?client_version={version}",
            {
                "authorization": f"Bearer {token}",
                "chatgpt-account-id": account,
                "originator": "codex_cli_rs",
            },
        )
        listed = catalog_models(body) if not problem else None
        if listed is None:
            return Status(
                name=name, answers=False, problem=problem or "the Codex model catalog is invalid"
            )
        return Status(name=name, answers=True, models=listed)

    async def _body(self, address: str, headers: dict[str, str]) -> tuple[str, str]:
        """The body of a 200 answer from `address` and no problem, else no body and the problem."""
        answer = await self.get(address, headers)
        if isinstance(answer, Silence):
            return "", answer.value
        if answer[0] != HTTP_OK:
            return "", f"HTTP {answer[0]}"
        return answer[1], ""

    async def local(self, targets: list[tuple[str, str, str]] | None = None) -> list[Found]:
        """The local servers among `targets` (kind, address, path) that answer, in their order."""
        wanted = targets or [
            (kind, next(k.base_url for k in KINDS if k.kind == kind), path)
            for kind, path in LOCAL_PROBES
        ]
        asked = await asyncio.gather(*(self._find(*target) for target in wanted))
        return [found for found in asked if found is not None]

    async def _find(self, kind: str, base: str, path: str) -> Found | None:
        answer = await self.get(f"{base}{path}", {})
        if isinstance(answer, Silence):
            return None
        state = local_state(kind, answer[0])
        if state is None:
            return None
        listed = models(answer[1]) if answer[0] == HTTP_OK else []
        return Found(kind=kind, base_url=base, state=state, models=listed)
