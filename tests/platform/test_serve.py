"""`code-factory serve` and `code-factory mcp` as real processes."""

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from sqlalchemy import text

from code_factory.app import MCP_TOKEN_VARIABLE
from code_factory.auth.service import AuthService
from code_factory.platform.config import DATABASE_URL_VARIABLE, Settings
from code_factory.platform.db import UnitOfWork, create_engine, create_session_factory

COMMAND = str(Path(sys.executable).parent / "code-factory")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def server(serve_env: dict[str, str]) -> Iterator[tuple[subprocess.Popen[str], int]]:
    port = free_port()
    env = {**serve_env, "CODE_FACTORY_PORT": str(port), "CODE_FACTORY_LOG_LEVEL": "INFO"}
    process = subprocess.Popen(  # noqa: S603  # our own console script, no shell
        [COMMAND, "serve"], env=env, stderr=subprocess.PIPE, text=True
    )
    try:
        yield process, port
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


def wait_ready(port: int, process: subprocess.Popen[str]) -> httpx.Response:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        assert process.poll() is None, "the server exited during startup"
        try:
            return httpx.get(f"http://127.0.0.1:{port}/api/ready", timeout=2)
        except httpx.TransportError:
            time.sleep(0.1)
    pytest.fail("the server did not start in 20 s")


def test_serve_answers_ready_and_stops_cleanly_on_sigterm(
    server: tuple[subprocess.Popen[str], int],
) -> None:
    process, port = server
    response = wait_ready(port, process)
    assert (response.status_code, response.json()) == (200, {"status": "ready"})
    # The docs are behind the sign-in guard: refused here, with the sentence naming the link.
    assert httpx.get(f"http://127.0.0.1:{port}/api/docs", timeout=2).status_code == 403

    process.send_signal(signal.SIGTERM)

    _, logs = process.communicate(timeout=15)
    # uvicorn finishes its graceful shutdown, then re-raises the signal so the parent sees how the
    # process was asked to stop: a clean stop is "terminated by SIGTERM", not a crash.
    assert process.returncode == -signal.SIGTERM
    assert '"message": "stopping"' in logs
    assert "Traceback" not in logs
    with pytest.raises(httpx.TransportError):
        httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=2)


async def test_mcp_over_stdio_serves_the_token_it_was_started_with(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    engine = create_engine(settings)
    try:
        # Committed on purpose: the server below is another process and reads the database itself.
        auth = AuthService(UnitOfWork(create_session_factory(engine)))
        issued = await auth.issue_owner_token("stdio process test", lifetime=timedelta(hours=1))
        transport = StdioTransport(
            command=COMMAND,
            args=["mcp"],
            env={
                **os.environ,
                DATABASE_URL_VARIABLE: os.environ[DATABASE_URL_VARIABLE],
                MCP_TOKEN_VARIABLE: issued.token.get_secret_value(),
            },
        )
        try:
            async with Client(transport) as client:
                names = [tool.name for tool in await client.list_tools()]
                who = await client.call_tool("whoami", {})
        finally:
            async with engine.begin() as cleanup:  # the row was committed: remove it
                await cleanup.execute(
                    text("delete from auth_tokens where id = :id"), {"id": issued.id}
                )
    finally:
        await engine.dispose()
    assert names[0] == "whoami"
    assert (who.structured_content or {})["subject"] == "owner:stdio process test"
