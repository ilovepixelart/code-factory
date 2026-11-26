import logging
import re

import httpx
import pytest
from starlette.types import Message, Receive, Scope, Send

from code_factory.platform.logging import request_id_var
from code_factory.platform.web.middleware import ErrorBoundary


async def test_a_request_id_is_generated_and_echoed(offline_client: httpx.AsyncClient) -> None:
    response = await offline_client.get("/api/health")
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


async def test_a_plain_caller_id_is_kept(offline_client: httpx.AsyncClient) -> None:
    response = await offline_client.get("/api/health", headers={"x-request-id": "abc.DEF_1-2"})
    assert response.headers["x-request-id"] == "abc.DEF_1-2"


async def test_an_id_that_could_forge_a_log_line_is_replaced(
    offline_client: httpx.AsyncClient,
) -> None:
    response = await offline_client.get("/api/health", headers={"x-request-id": 'a b"c'})
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])


async def test_the_access_record_carries_the_request_id_and_the_outcome(
    offline_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    await offline_client.get("/api/about", headers={"x-request-id": "req-7"})
    (record,) = [r for r in caplog.records if r.name == "code_factory.platform.web.middleware"]
    fields = record.__dict__
    assert (fields["request_id"], fields["method"], fields["path"], fields["status"]) == (
        "req-7",
        "GET",
        "/api/about",
        200,
    )


async def test_the_request_id_does_not_outlive_the_request(
    offline_client: httpx.AsyncClient,
) -> None:
    await offline_client.get("/api/health", headers={"x-request-id": "req-leak"})
    assert request_id_var.get() is None


@pytest.mark.parametrize("path", ["/api/health", "/api/nothing-here", "/api/docs"])
async def test_every_answer_carries_the_security_headers(
    offline_client: httpx.AsyncClient, path: str
) -> None:
    headers = (await offline_client.get(path)).headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cross-origin-opener-policy"] == "same-origin"
    directives = dict(
        part.strip().split(" ", 1) for part in headers["content-security-policy"].split(";")
    )
    assert directives["default-src"] == "'none'"
    assert directives["script-src"] == "'self'"
    # Inline styles only: shadcn-vue's chart (Unovis) sets its colours as style attributes and
    # <style> elements; scripts stay same-origin with nothing inline or evaluated.
    assert directives["style-src"] == "'self' 'unsafe-inline'"
    assert "unsafe-eval" not in headers["content-security-policy"]


async def test_a_failure_after_the_response_started_is_logged_and_nothing_more_is_sent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def app(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        msg = "failed while streaming"
        raise RuntimeError(msg)

    async def receive() -> Message:
        return {"type": "http.request"}

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    boundary = ErrorBoundary(app)
    with pytest.raises(RuntimeError, match="failed while streaming"):
        await boundary({"type": "http"}, receive, send)
    assert [message["type"] for message in sent] == ["http.response.start"]
    assert sent[0]["status"] == 200
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR] == [
        "unhandled error"
    ]
