"""Deleting a ticket, column limits, checks, merge and flow over HTTP."""

from pathlib import Path

import httpx
from fastapi import FastAPI

from code_factory.repositories.service import RepositoryService
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService


async def _tracked_ticket(
    app: FastAPI, tmp_path: Path, title: str = "Delete me"
) -> tuple[str, str]:
    services = app.state.services
    root = tmp_path / "writes-repo"
    root.mkdir(exist_ok=True)
    record = await services.get(RepositoryService).track(root)
    ticket = await services.get(TicketService).create(
        NewTicket(repository=record.name, title=title), by="owner"
    )
    return str(record.name), str(ticket.id)


async def test_a_deleted_ticket_is_gone_and_its_answer_carries_an_undo(
    client: httpx.AsyncClient, app: FastAPI, tmp_path: Path
) -> None:
    repository, ticket = await _tracked_ticket(app, tmp_path)

    deleted = await client.delete(f"/api/tickets/{repository}/{ticket}")
    page = await client.get(f"/api/tickets/{repository}/{ticket}")

    assert deleted.status_code == 200
    assert deleted.json()["undo"]
    assert page.status_code == 404


async def test_a_column_limit_is_set_cleared_and_refused_for_an_unknown_stage(
    client: httpx.AsyncClient,
) -> None:
    put = await client.put("/api/columns/build/limit", json={"limit": 3})
    cleared = await client.put("/api/columns/build/limit", json={"limit": None})
    odd = await client.put("/api/columns/deploy/limit", json={"limit": 3})

    assert (put.status_code, cleared.status_code) == (200, 200)
    assert (odd.status_code, odd.json()["detail"]) == (400, "unknown stage deploy")


async def test_checks_and_merge_of_an_unknown_ticket_are_404(client: httpx.AsyncClient) -> None:
    checks = await client.post("/api/tickets/sample/CF-999999/checks")
    merge = await client.post("/api/tickets/sample/CF-999999/merge")

    assert (checks.status_code, merge.status_code) == (404, 404)


async def test_a_ticket_with_no_pull_request_does_not_merge(
    client: httpx.AsyncClient, app: FastAPI, tmp_path: Path
) -> None:
    repository, ticket = await _tracked_ticket(app, tmp_path, "Nothing shipped")

    response = await client.post(f"/api/tickets/{repository}/{ticket}/merge")

    assert (response.status_code, response.json()["detail"]) == (
        409,
        "its pull request is not open and green",
    )


async def test_flow_refuses_an_unknown_range(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/flow?range=1y")
    week = await client.get("/api/flow")

    assert response.status_code == 400
    assert [e["pointer"] for e in response.json()["errors"]] == ["/query/range"]
    assert (week.status_code, week.json()["range"]) == (200, "7d")
