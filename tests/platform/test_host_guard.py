"""DNS rebinding: a page on another origin can resolve its own name to 127.0.0.1 and call the
server from the owner's browser. The `Host` it sends names its own domain, so refusing every Host
that is not a loopback name (and every foreign `Origin` on the MCP endpoint) closes that door.
"""

import httpx
import pytest
from fastapi import FastAPI

from code_factory.platform.config import Settings

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "probe", "version": "0"},
    },
}
MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


def _host(port: int, name: str) -> str:
    return name.replace("PORT", str(port))


@pytest.mark.parametrize(
    "host",
    ["localhost", "localhost:PORT", "127.0.0.1:PORT", "[::1]:PORT", "[::1]", "LOCALHOST:PORT"],
)
async def test_a_loopback_host_passes(
    offline_client: httpx.AsyncClient, offline_settings: Settings, host: str
) -> None:
    response = await offline_client.get(
        "/api/health", headers={"host": _host(offline_settings.port, host)}
    )
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "evil.example:PORT",
        "localhost.evil.example",
        "localhost:9999",
        "127.0.0.1:PORT.evil.example",
        "[::2]:PORT",
        "10.0.0.5:PORT",
        "",
    ],
)
async def test_any_other_host_is_refused_with_the_error_body(
    offline_client: httpx.AsyncClient, offline_settings: Settings, host: str
) -> None:
    response = await offline_client.get(
        "/api/health", headers={"host": _host(offline_settings.port, host)}
    )
    assert (response.status_code, response.json()["detail"]) == (400, "invalid host header")
    assert response.headers["x-request-id"]
    assert "content-security-policy" in response.headers


async def test_the_mcp_endpoint_refuses_a_foreign_host(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/mcp/", json=INITIALIZE, headers={**MCP_HEADERS, "host": "evil.example"}
    )
    assert response.status_code in {400, 421}


async def test_the_mcp_endpoint_refuses_a_foreign_origin(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/mcp/", json=INITIALIZE, headers={**MCP_HEADERS, "origin": "http://evil.example"}
    )
    assert response.status_code == 403


async def test_the_mcp_endpoint_lets_a_loopback_host_and_origin_reach_the_bearer_check(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    port = app.state.settings.port
    response = await client.post(
        "/mcp/",
        json=INITIALIZE,
        headers={
            **MCP_HEADERS,
            "host": f"localhost:{port}",
            "origin": f"http://localhost:{port}",
        },
    )
    # Past the host and origin guards the request meets the bearer check: no token, 401.
    assert response.status_code == 401


# The session cookie belongs to the host name it was set on, and every link the board prints (the
# sign-in link, `code-factory open`) names 127.0.0.1. A page opened on another loopback name moves
# there, so a sign-in on one name is never missing on the other.
@pytest.mark.parametrize("host", ["localhost:PORT", "localhost", "[::1]:PORT", "LOCALHOST:PORT"])
@pytest.mark.parametrize("path", ["/tickets?view=list", "/owner/cfn_value", "/"])
async def test_a_page_asked_on_another_loopback_name_moves_to_127_0_0_1(
    offline_client: httpx.AsyncClient, offline_settings: Settings, host: str, path: str
) -> None:
    response = await offline_client.get(
        path, headers={"host": _host(offline_settings.port, host)}, follow_redirects=False
    )
    assert (response.status_code, response.headers.get("location")) == (
        308,
        f"http://127.0.0.1:{offline_settings.port}{path}",
    )


async def test_a_page_asked_on_127_0_0_1_is_answered_there(
    offline_client: httpx.AsyncClient, offline_settings: Settings
) -> None:
    response = await offline_client.get(
        "/tickets",
        headers={"host": f"127.0.0.1:{offline_settings.port}"},
        follow_redirects=False,
    )
    assert response.status_code != 308


@pytest.mark.parametrize("path", ["/api/health", "/mcp"])
async def test_the_api_and_the_mcp_endpoint_never_move(
    offline_client: httpx.AsyncClient, offline_settings: Settings, path: str
) -> None:
    response = await offline_client.get(
        path,
        headers={"host": f"localhost:{offline_settings.port}", **MCP_HEADERS},
        follow_redirects=False,
    )
    assert response.status_code != 308


async def test_a_change_on_another_loopback_name_is_not_moved(
    offline_client: httpx.AsyncClient, offline_settings: Settings
) -> None:
    response = await offline_client.post(
        "/tickets", headers={"host": f"localhost:{offline_settings.port}"}, follow_redirects=False
    )
    assert response.status_code != 308
