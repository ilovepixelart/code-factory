"""The runs routes over HTTP: holding agents, a run's stop and log, usage, starts and previews."""

from pathlib import Path

import httpx
from fastapi import FastAPI

from code_factory.repositories.service import RepositoryService
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService


async def test_holding_agents_sets_halted_at_and_resuming_clears_it(
    client: httpx.AsyncClient,
) -> None:
    before = (await client.get("/api/agents")).json()
    stopped = await client.post("/api/agents/stop")
    held = (await client.get("/api/agents")).json()
    resumed = await client.post("/api/agents/resume")
    after = (await client.get("/api/agents")).json()

    assert before == {"halted_at": None}
    assert stopped.json() == {
        "notice": "Stopped 0 agents; agents are held until resumed",
        "undo": None,
    }
    assert isinstance(held["halted_at"], float)
    assert resumed.json() == {"notice": "Agents may start again", "undo": None}
    assert after == {"halted_at": None}


async def test_an_unknown_runs_stop_and_log_are_404(client: httpx.AsyncClient) -> None:
    stop = await client.post("/api/runs/no-such-run/stop")
    log = await client.get("/api/runs/no-such-run/log")

    assert (stop.status_code, log.status_code) == (404, 404)


async def test_usage_answers_rows_or_csv(client: httpx.AsyncClient) -> None:
    rows = await client.get("/api/usage")
    csv = await client.get("/api/usage?format=csv")

    assert (rows.status_code, rows.json()) == (200, [])
    assert csv.headers["content-type"].startswith("text/csv")


async def test_a_start_on_an_unknown_ticket_is_404_and_an_unknown_field_400(
    client: httpx.AsyncClient,
) -> None:
    unknown = await client.post("/api/tickets/sample/CF-999999/runs")
    odd = await client.post("/api/tickets/sample/CF-1/runs", json={"looping": True})

    assert unknown.status_code == 404
    assert odd.status_code == 400
    assert [e["pointer"] for e in odd.json()["errors"]] == ["/body/looping"]


async def test_the_start_body_the_board_sends_passes_validation(
    client: httpx.AsyncClient,
) -> None:
    sent = await client.post(
        "/api/tickets/sample/CF-999999/runs",
        json={"permissions": "bypassPermissions", "loop": True},
    )

    assert sent.status_code == 404


async def test_a_ticket_without_a_preview_command_has_none_configured(
    client: httpx.AsyncClient, app: FastAPI, tmp_path: Path
) -> None:
    services = app.state.services
    root = tmp_path / "preview-repo"
    root.mkdir()
    record = await services.get(RepositoryService).track(root)
    ticket = await services.get(TicketService).create(
        NewTicket(repository=record.name, title="Preview me"), by="owner"
    )

    response = await client.get(f"/api/tickets/{record.name}/{ticket.id}/preview")

    assert response.status_code == 200, response.json()
    assert (response.json()["configured"], response.json()["running"]) == (False, False)


async def test_a_ticket_of_an_untracked_repository_has_no_preview(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    ticket = await app.state.services.get(TicketService).create(
        NewTicket(repository="untracked-here", title="Nowhere"), by="owner"
    )

    response = await client.get(f"/api/tickets/untracked-here/{ticket.id}/preview")

    assert (response.status_code, response.json()["detail"]) == (404, "unknown repository")
