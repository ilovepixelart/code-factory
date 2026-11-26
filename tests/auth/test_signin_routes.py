"""The owner's sign-in through the app: the link, the cookie, the guard behind it."""

from datetime import timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from code_factory.auth.service import AuthService
from code_factory.platform.db import UnitOfWork

COOKIE = "code_factory_owner"
SPENT = "this sign-in link is spent or unknown: run `code-factory sign-in` for a new one"


@pytest.fixture
def auth(connection: AsyncConnection) -> AuthService:
    return AuthService(
        UnitOfWork(
            async_sessionmaker(
                bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
        )
    )


async def _nonce(auth: AuthService) -> str:
    return (await auth.issue_sign_in_nonce("owner")).token.get_secret_value()


async def test_the_link_sets_the_session_cookie_and_sends_the_owner_to_the_board(
    guarded_client: httpx.AsyncClient, auth: AuthService
) -> None:
    response = await guarded_client.get(f"/owner/{await _nonce(auth)}")

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=cfs_")
    assert {"HttpOnly", "SameSite=strict", "Path=/"} <= {p.strip() for p in cookie.split(";")}


@pytest.mark.parametrize(("scheme", "secure"), [("https", True), ("http", False)])
async def test_the_cookie_is_secure_exactly_when_the_link_came_over_https(
    guarded_client: httpx.AsyncClient, auth: AuthService, scheme: str, *, secure: bool
) -> None:
    response = await guarded_client.get(f"{scheme}://127.0.0.1/owner/{await _nonce(auth)}")

    assert response.status_code == 303
    parts = {p.strip() for p in response.headers["set-cookie"].split(";")}
    assert ("Secure" in parts) is secure


async def test_the_cookie_opens_the_api_the_guard_closed(
    guarded_client: httpx.AsyncClient, auth: AuthService
) -> None:
    assert (await guarded_client.get("/api/about")).status_code == 403
    signed = await guarded_client.get(f"/owner/{await _nonce(auth)}")
    value = signed.headers["set-cookie"].split(";")[0]

    response = await guarded_client.get("/api/about", headers={"cookie": value})

    assert response.status_code == 200


async def test_a_link_works_once(guarded_client: httpx.AsyncClient, auth: AuthService) -> None:
    link = f"/owner/{await _nonce(auth)}"
    assert (await guarded_client.get(link)).status_code == 303

    again = await guarded_client.get(link)

    assert (again.status_code, again.json()["detail"]) == (403, SPENT)
    assert "set-cookie" not in again.headers


async def test_an_unknown_value_is_refused_the_same_way(guarded_client: httpx.AsyncClient) -> None:
    response = await guarded_client.get("/owner/not-a-token")
    assert (response.status_code, response.json()["detail"]) == (403, SPENT)


async def test_a_session_cookie_is_not_a_sign_in_link(
    guarded_client: httpx.AsyncClient, auth: AuthService
) -> None:
    session = await auth.redeem_sign_in_nonce(await _nonce(auth), lifetime=timedelta(days=1))
    assert session is not None
    response = await guarded_client.get(f"/owner/{session.token.get_secret_value()}")
    assert response.status_code == 403


async def test_an_owner_mcp_token_is_not_a_session_cookie(
    guarded_client: httpx.AsyncClient, auth: AuthService
) -> None:
    owner = await auth.issue_owner_token("laptop", lifetime=timedelta(days=1))
    cookie = f"{COOKIE}={owner.token.get_secret_value()}"
    response = await guarded_client.get("/api/about", headers={"cookie": cookie})
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("asked", "landing"),
    [
        ("/tickets/sample/CF-1", "/tickets/sample/CF-1"),
        ("/memory?x=1", "/memory?x=1"),
        ("https://evil.example/", "/"),
        ("//evil.example/", "/"),
        ("/\\evil.example", "/"),
        ("/api/tickets", "/"),
        ("/owner/x", "/"),
        ("", "/"),
    ],
)
async def test_the_owner_lands_only_on_a_page_of_the_board(
    guarded_client: httpx.AsyncClient, auth: AuthService, asked: str, landing: str
) -> None:
    response = await guarded_client.get(f"/owner/{await _nonce(auth)}", params={"to": asked})
    assert (response.status_code, response.headers["location"]) == (303, landing)


async def test_the_link_value_is_in_no_log_record(
    guarded_client: httpx.AsyncClient, auth: AuthService, caplog: pytest.LogCaptureFixture
) -> None:
    nonce = await _nonce(auth)
    with caplog.at_level("DEBUG"):
        await guarded_client.get(f"/owner/{nonce}")
    ours = [r for r in caplog.records if r.name.startswith("code_factory")]
    assert any(r.getMessage() == "request" for r in ours)
    assert nonce not in "".join(f"{r.getMessage()} {r.__dict__}" for r in ours)
