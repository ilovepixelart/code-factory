import logging

import pytest
from starlette.types import Message, Receive, Scope, Send

from code_factory.platform.web.middleware import ErrorBoundary


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
