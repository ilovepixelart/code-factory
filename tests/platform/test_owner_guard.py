"""The sign-in guard and the same-origin rule on the API, through the whole app."""

from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest

from code_factory.app import MODULES, build_resources, build_services
from code_factory.auth.service import AuthService
from code_factory.platform.config import Settings
from code_factory.platform.mcp.access import Access
from code_factory.platform.web.app import WebOptions, create_web_app

GOOD = "good-session"
READ_REFUSAL = "reading the board needs the owner's sign-in: run uv run code-factory open"
WRITE_REFUSAL = "a change needs the owner's sign-in: run uv run code-factory open"
SIGNED = {"cookie": f"other=1; code_factory_owner={GOOD}"}


async def _check(cookie: str) -> bool:
    return cookie == GOOD


@pytest.fixture
async def client(offline_settings: Settings, tmp_path: Path) -> AsyncGenerator[httpx.AsyncClient]:
    resources = build_resources(offline_settings)
    services = build_services(resources)
    app = create_web_app(
        resources,
        services=services,
        modules=MODULES,
        mcp_access=Access(verifier=services.get(AuthService)),
        options=WebOptions(app_dir=tmp_path, session_check=_check),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        yield client


async def test_a_read_without_the_cookie_is_refused_naming_the_link(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/about")
    assert (response.status_code, response.json()["detail"]) == (403, READ_REFUSAL)


async def test_a_read_with_a_session_cookie_the_service_accepts_is_served(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.get("/api/about", headers=SIGNED)).status_code == 200


async def test_a_cookie_the_service_refuses_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/about", headers={"cookie": "code_factory_owner=bad"})
    assert response.status_code == 403


@pytest.mark.parametrize(
    "path", ["/api/openapi.json", "/api/docs", "/api/docs-assets/docs-init.js"]
)
async def test_the_api_description_and_swagger_are_behind_the_guard(
    client: httpx.AsyncClient, path: str
) -> None:
    assert (await client.get(path)).status_code == 403
    assert (await client.get(path, headers=SIGNED)).status_code == 200


@pytest.mark.parametrize(
    "path", ["/api/health", "/api/ready", "/", "/tickets/sample/CF-1", "/favicon.svg"]
)
async def test_probes_and_the_app_shell_need_no_sign_in(
    client: httpx.AsyncClient, path: str
) -> None:
    assert (await client.get(path)).status_code != 403


async def test_a_write_without_the_cookie_is_refused_before_the_route_is_looked_up(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/api/nowhere", json={})
    assert (response.status_code, response.json()["detail"]) == (403, WRITE_REFUSAL)


async def test_a_preflight_is_not_refused_for_want_of_a_cookie(client: httpx.AsyncClient) -> None:
    assert (await client.options("/api/about")).status_code != 403


@pytest.mark.parametrize(
    "headers",
    [{"origin": "http://evil.example"}, {"sec-fetch-site": "cross-site"}],
)
async def test_a_write_from_another_origin_is_refused_even_when_signed_in(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.post("/api/nowhere", json={}, headers={**SIGNED, **headers})
    assert (response.status_code, response.json()["detail"]) == (
        403,
        "changes are made from the board's own pages",
    )


async def test_a_write_from_the_boards_own_origin_reaches_the_route(
    client: httpx.AsyncClient,
) -> None:
    headers = {**SIGNED, "origin": "http://127.0.0.1", "sec-fetch-site": "same-origin"}
    assert (await client.post("/api/nowhere", json={}, headers=headers)).status_code == 404


async def test_a_write_with_a_body_that_is_not_json_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/nowhere", content=b"x", headers={**SIGNED, "content-type": "text/plain"}
    )
    assert (response.status_code, response.json()["detail"]) == (415, "changes are sent as JSON")


async def test_a_write_with_no_body_and_no_content_type_is_let_through(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.delete("/api/nowhere", headers=SIGNED)).status_code == 404


@pytest.mark.parametrize("path", ["/api/agent-definitions", "/api/connections/x"])
async def test_agent_and_connection_changes_need_an_origin_header(
    client: httpx.AsyncClient, path: str
) -> None:
    response = await client.post(path, json={}, headers=SIGNED)
    assert (response.status_code, response.json()["detail"]) == (
        403,
        "agents and connections are changed from the board's own pages",
    )
    again = await client.post(path, json={}, headers={**SIGNED, "origin": "http://127.0.0.1"})
    assert again.status_code != 403  # past the guard: the route answers for itself
