import logging

import httpx
import pytest
from fastapi import APIRouter, FastAPI, HTTPException

from code_factory.platform.errors import (
    BadRequestError,
    CodeFactoryError,
    ConflictError,
    GoneError,
    NotFoundError,
    UnavailableError,
)

LEAK_MARKER = "password=hunter2 in /srv/internal/path"
# The standard reason phrases (RFC 9110 section 15), the title of an `about:blank` problem.
TITLES = {
    400: "Bad Request", 401: "Unauthorized", 404: "Not Found", 405: "Method Not Allowed",
    409: "Conflict", 410: "Gone", 500: "Internal Server Error", 503: "Service Unavailable",
}  # fmt: skip


def _problem(status: int, detail: str) -> dict[str, object]:
    return {"type": "about:blank", "title": TITLES[status], "status": status, "detail": detail}


_RAISES: dict[str, Exception] = {
    "bad-request": BadRequestError("the name must not be empty"),
    "not-found": NotFoundError("ticket CF-1 does not exist"),
    "conflict": ConflictError("ticket CF-1 is already archived"),
    "gone": GoneError("nothing to undo any more"),
    "unavailable": UnavailableError("the database is not reachable"),
    "unmapped": CodeFactoryError("something the person can read"),
}


@pytest.fixture
async def client(offline_app: FastAPI) -> httpx.AsyncClient:
    router = APIRouter()

    def make(error: Exception):  # noqa: ANN202
        async def raise_it() -> None:
            raise error

        return raise_it

    for name, error in _RAISES.items():
        router.add_api_route(f"/api/test/{name}", make(error))

    @router.get("/api/test/crash")
    async def crash() -> None:
        raise RuntimeError(LEAK_MARKER)

    @router.get("/api/test/guarded")
    async def guarded() -> None:
        raise HTTPException(401, "sign in", headers={"WWW-Authenticate": "Bearer"})

    @router.get("/api/test/number")
    async def number(n: int) -> dict[str, int]:
        return {"n": n}

    offline_app.include_router(router)
    transport = httpx.ASGITransport(app=offline_app)
    return httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1")


@pytest.mark.parametrize(
    ("name", "status"),
    [
        ("bad-request", 400),
        ("not-found", 404),
        ("conflict", 409),
        ("gone", 410),
        ("unavailable", 503),
        ("unmapped", 500),
    ],
)
async def test_each_error_class_answers_its_status_with_its_sentence(
    client: httpx.AsyncClient, name: str, status: int
) -> None:
    response = await client.get(f"/api/test/{name}")
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank", "title": TITLES[status], "status": status,
        "detail": str(_RAISES[name]),
    }  # fmt: skip


async def test_an_unknown_api_path_is_a_json_404_not_a_page(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/nothing-here")
    assert (response.status_code, response.json()) == (404, _problem(404, "not found"))


async def test_a_wrong_method_is_a_json_405(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/health")
    assert (response.status_code, response.json()) == (405, _problem(405, "method not allowed"))


async def test_a_405_keeps_its_allow_header(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/health")
    assert response.headers["allow"] == "GET"


async def test_an_http_exception_keeps_its_headers(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/test/guarded")
    assert (response.status_code, response.json()) == (401, _problem(401, "sign in"))
    assert response.headers["www-authenticate"] == "Bearer"


async def test_an_invalid_query_is_a_400_pointing_at_the_field(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/test/number", params={"n": "abc"})
    body = response.json()
    assert (response.status_code, body["title"], body["status"]) == (400, "Bad Request", 400)
    assert body["detail"].startswith("invalid request: query.n: ")
    assert [e["pointer"] for e in body["errors"]] == ["/query/n"]


async def test_an_unexpected_exception_is_logged_with_its_request_id_and_hidden_from_the_caller(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR)
    response = await client.get("/api/test/crash", headers={"x-request-id": "req-crash-1"})
    assert response.status_code == 500
    assert response.json() == _problem(500, "internal error")
    assert LEAK_MARKER not in response.text
    assert response.headers["x-request-id"] == "req-crash-1"
    assert "content-security-policy" in response.headers
    logged = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(logged) == 1
    assert logged[0].__dict__["request_id"] == "req-crash-1"
    exc_info = logged[0].exc_info
    assert isinstance(exc_info, tuple)
    assert LEAK_MARKER in str(exc_info[1])
