"""The Inbox routes over HTTP: the page with its tag, the count, permission answers and rules."""

from datetime import UTC, datetime

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.runs.models import PermissionRequest
from code_factory.runs.repository.permissions import PermissionRepository
from code_factory.talk.service import TalkService
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService

PROBLEM = "application/problem+json"


async def _ticket_with_question(app: FastAPI) -> str:
    services = app.state.services
    ticket = await services.get(TicketService).create(
        NewTicket(repository="sample", title="Pick a palette"), by="owner"
    )
    await services.get(TalkService).ask(ticket.id, "Which colour?", [], by="agent")
    return str(ticket.id)


async def _pending(db_session: AsyncSession, request_id: str = "aaaaaaaaaaaa") -> None:
    await PermissionRepository(db_session).add_request(
        PermissionRequest(
            id=request_id,
            repository="sample",
            ticket_key="CF-1",
            tool="Bash",
            summary="npm test --watch",
            kind="Bash(npm *)",
            requested_at=datetime.now(UTC),
        )
    )
    await db_session.flush()


async def test_the_inbox_lists_an_open_question_and_counts_it(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    ticket = await _ticket_with_question(app)

    page = await client.get("/api/inbox")
    count = await client.get("/api/inbox/count")

    assert page.status_code == 200
    [item] = page.json()["questions"]
    assert (item["ticket"]["id"], item["question"]["text"]) == (ticket, "Which colour?")
    assert count.json() == {"count": 1, "latest": f"{ticket} asks: Which colour?"}


async def test_an_unchanged_inbox_answers_304_to_its_own_tag(client: httpx.AsyncClient) -> None:
    first = await client.get("/api/inbox")
    tag = first.headers["etag"]

    again = await client.get("/api/inbox", headers={"If-None-Match": f'"other", W/{tag}'})
    stale = await client.get("/api/inbox", headers={"If-None-Match": '"other"'})

    assert (again.status_code, again.content) == (304, b"")
    assert stale.status_code == 200


async def test_allowing_a_request_answers_its_notice_and_a_second_answer_conflicts(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _pending(db_session)

    allowed = await client.post("/api/permissions/aaaaaaaaaaaa/allow")
    again = await client.post("/api/permissions/aaaaaaaaaaaa/deny")

    assert allowed.json() == {"notice": "Allowed Bash on CF-1", "undo": None}
    assert (again.status_code, again.headers["content-type"]) == (409, PROBLEM)
    assert again.json()["detail"] == "this request is already answered"


async def test_an_unknown_request_is_404_and_an_unknown_verdict_400(
    client: httpx.AsyncClient,
) -> None:
    unknown = await client.post("/api/permissions/bbbbbbbbbbbb/deny")
    odd = await client.post("/api/permissions/bbbbbbbbbbbb/maybe")

    assert (unknown.status_code, unknown.json()["detail"]) == (404, "no such permission request")
    assert odd.status_code == 400
    assert [e["pointer"] for e in odd.json()["errors"]] == ["/path/verdict"]


async def test_a_kind_never_suggested_is_not_adopted(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/permissions/rules", json={"kind": "Bash(rm *)"})

    assert response.status_code == 409


async def test_a_rule_body_with_an_unknown_field_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/permissions/rules", json={"kind": "x", "always": True})

    assert response.status_code == 400
    assert [e["pointer"] for e in response.json()["errors"]] == ["/body/always"]


async def test_a_browser_that_is_not_signed_in_gets_no_inbox(
    guarded_client: httpx.AsyncClient,
) -> None:
    page = await guarded_client.get("/api/inbox")
    answer = await guarded_client.post("/api/permissions/aaaaaaaaaaaa/allow")

    assert (page.status_code, answer.status_code) == (403, 403)
