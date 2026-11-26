"""Bearer tokens over the mounted `/mcp`, against the real auth service and database."""

import logging
from collections.abc import AsyncGenerator
from datetime import timedelta

import httpx2
import pytest
from fastapi import FastAPI
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp.shared.exceptions import MCPError
from sqlalchemy import text

from app_lifespan import running_lifespan
from code_factory.app import create_app
from code_factory.auth.service import AuthService
from code_factory.platform.config import Settings
from code_factory.platform.db import create_engine

HOUR = timedelta(hours=1)
# The revision each client mode settles on with this server.
VERSIONS = {"legacy": "2025-11-25", "auto": "2026-07-28"}


def _client(app: FastAPI, token: str | None, mode: str) -> Client[StreamableHttpTransport]:
    def in_process(
        headers: dict[str, str] | None = None,
        timeout: httpx2.Timeout | None = None,
        auth: httpx2.Auth | None = None,
        follow_redirects: bool = True,
    ) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            headers=headers,
            timeout=timeout,
            auth=auth,
            follow_redirects=follow_redirects,
        )

    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    transport = StreamableHttpTransport(
        "http://localhost/mcp/", headers=headers, httpx_client_factory=in_process
    )
    return Client(transport, mode=mode)


@pytest.fixture(params=["legacy", "auto"])
def mode(request: pytest.FixtureRequest) -> str:
    """Both protocol paths: `legacy` is the initialize handshake of the 2025-11-25 revision,
    `auto` the 2026-07-28 revision's server/discover, which current clients use first."""
    return str(request.param)


def _auth(app: FastAPI) -> AuthService:
    auth = app.state.services.get(AuthService)
    assert isinstance(auth, AuthService)
    return auth


@pytest.fixture
async def app(settings: Settings, migrated: None) -> AsyncGenerator[FastAPI]:  # noqa: ARG001
    """The app on its own pooled connections: an MCP client runs requests concurrently, which
    the one rolled-back connection of the shared fixture cannot serve. The tokens these tests
    issue are committed, so they are deleted afterwards."""
    application = create_app(settings)
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            before = (
                await connection.execute(text("select coalesce(max(id), 0) from auth_tokens"))
            ).scalar_one()
        async with running_lifespan(application):
            yield application
    finally:
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("delete from auth_tokens where id > :before"), {"before": before}
                )
        finally:
            await engine.dispose()


async def test_an_owner_token_completes_the_handshake_and_is_known_as_that_owner(
    app: FastAPI,
    mode: str,
) -> None:
    issued = await _auth(app).issue_owner_token("laptop", lifetime=HOUR)
    async with _client(app, issued.token.get_secret_value(), mode) as client:
        server, version = client.server_info, client.protocol_version
        who = await client.call_tool("whoami", {})
    assert (who.structured_content or {})["subject"] == "owner:laptop"
    assert server is not None
    assert (server.name, version) == ("code-factory", VERSIONS[mode])


async def test_a_run_token_is_bound_to_its_ticket_and_stage(app: FastAPI, mode: str) -> None:
    issued = await _auth(app).issue_run_token(
        run_id="r7", ticket_id="CF-12", stage="build", repository="/r", lifetime=HOUR
    )
    async with _client(app, issued.token.get_secret_value(), mode) as client:
        who = (await client.call_tool("whoami", {})).structured_content or {}
    assert (who["role"], who["subject"], who["ticket_id"], who["stage"]) == (
        "run",
        "run:r7",
        "CF-12",
        "build",
    )
    assert who["writable_documents"] == ["notes"]


@pytest.mark.parametrize("token", [None, "garbage", "cfo_" + "A" * 43])
async def test_a_missing_or_unknown_token_is_answered_401_before_any_tool_runs(
    app: FastAPI, token: str | None
) -> None:
    headers = {"accept": "application/json, text/event-stream"}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as http:
        response = await http.post(
            "/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=headers
        )
    assert response.status_code == 401


async def test_a_token_revoked_between_two_calls_stops_working_at_once(
    app: FastAPI, mode: str
) -> None:
    auth = _auth(app)
    issued = await auth.issue_run_token(
        run_id="r8", ticket_id="CF-1", stage="spec", repository="/r", lifetime=HOUR
    )
    async with _client(app, issued.token.get_secret_value(), mode) as client:
        await client.call_tool("whoami", {})
        await auth.revoke_run("r8")
        with pytest.raises(MCPError):
            await client.call_tool("whoami", {})


async def test_the_token_appears_in_no_log_record(
    app: FastAPI, mode: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    issued = await _auth(app).issue_owner_token("quiet", lifetime=HOUR)
    token = issued.token.get_secret_value()
    async with _client(app, token, mode) as client:
        await client.call_tool("whoami", {})
    assert token not in caplog.text
