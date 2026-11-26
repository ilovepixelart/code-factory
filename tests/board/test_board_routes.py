"""The board's own routes: saved views, the inbox count, repositories and templates."""

from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI

from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.sample.service import SampleService
from code_factory.talk.models import Choice
from code_factory.talk.service import TalkService


@pytest.fixture
async def ids(app: FastAPI) -> dict[str, str]:
    services = cast("Services", app.state.services)
    return await services.get(SampleService).load("board")


async def test_a_saved_view_is_listed_in_the_order_saved_and_can_be_deleted(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/api/views", json={"name": "Bugs", "query": "type=bug"})
    await client.post("/api/views", json={"name": "Alex", "query": "assignee=alex"})

    listed = (await client.get("/api/views")).json()
    deleted = await client.delete("/api/views/Bugs")
    after = (await client.get("/api/views")).json()

    assert listed == [
        {"name": "Bugs", "query": "type=bug"},
        {"name": "Alex", "query": "assignee=alex"},
    ]
    assert deleted.status_code == 200
    assert [v["name"] for v in after] == ["Alex"]


async def test_a_view_without_a_name_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/views", json={"name": "   ", "query": "x=1"})
    assert (response.status_code, response.json()["detail"]) == (400, "A view needs a name")


async def test_deleting_a_view_that_is_not_saved_is_404(client: httpx.AsyncClient) -> None:
    response = await client.delete("/api/views/nope")
    assert (response.status_code, response.json()["detail"]) == (404, "No view with this name")


async def test_saving_a_view_under_a_taken_name_is_a_conflict(client: httpx.AsyncClient) -> None:
    await client.post("/api/views", json={"name": "Bugs", "query": "type=bug"})
    again = await client.post("/api/views", json={"name": "Bugs", "query": "type=feature"})
    assert (again.status_code, again.json()["detail"]) == (
        409,
        "A view with this name already exists",
    )
    assert (await client.get("/api/views")).json() == [{"name": "Bugs", "query": "type=bug"}]


async def test_nothing_waiting_is_a_count_of_zero(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/inbox/count")).json() == {"count": 0, "latest": ""}


async def test_each_open_question_counts_and_the_newest_is_named(
    app: FastAPI, client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    talk = cast("Services", app.state.services).get(TalkService)
    await talk.ask(
        ids["Specs written"], "Which colour?", [Choice(text="red"), Choice(text="blue")], by="run:1"
    )
    await talk.ask(ids["A bug in flight"], "Which size?", [], by="run:1")

    answer = (await client.get("/api/inbox/count")).json()

    assert answer["count"] == 2
    assert answer["latest"] == f"{ids['A bug in flight']} asks: Which size?"


async def test_the_board_cards_count_their_open_questions(
    app: FastAPI, client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    talk = cast("Services", app.state.services).get(TalkService)
    await talk.ask(ids["Specs written"], "Which colour?", [], by="run:1")

    columns = (await client.get("/api/board")).json()["columns"]

    asked = {c["id"]: c["open_questions"] for cards in columns.values() for c in cards}
    assert (asked[ids["Specs written"]], asked[ids["A bug in flight"]]) == (1, 0)
    filtered = (await client.get("/api/tickets?questions=1")).json()["columns"]
    assert [c["id"] for cards in filtered.values() for c in cards] == [ids["Specs written"]]


async def test_a_tracked_repository_is_listed_with_the_ones_tickets_are_filed_in(
    app: FastAPI, client: httpx.AsyncClient, ids: dict[str, str], tmp_path: Path
) -> None:
    del ids
    root = tmp_path / "tracked"
    root.mkdir()
    await cast("Services", app.state.services).get(RepositoryService).track(root)

    assert (await client.get("/api/repositories")).json() == ["sample", "second", "tracked"]


async def test_a_ticket_template_is_the_tracked_repositorys_file(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path
) -> None:
    root = tmp_path / "tracked"
    (root / ".code-factory" / "templates").mkdir(parents=True)
    (root / ".code-factory" / "templates" / "ticket-bug.md").write_text("## Steps\n")
    await cast("Services", app.state.services).get(RepositoryService).track(root)

    bug = await client.get("/api/repositories/tracked/templates/bug")
    feature = await client.get("/api/repositories/tracked/templates/feature")
    untracked = await client.get("/api/repositories/nowhere/templates/bug")

    assert (bug.json(), feature.json(), untracked.json()) == (
        {"text": "## Steps\n"},
        {"text": ""},
        {"text": ""},
    )
    wrong = await client.get("/api/repositories/nowhere/templates/epic")
    assert (wrong.status_code, wrong.json()["detail"]) == (400, "unknown type epic")


async def test_a_new_install_offers_no_repository_until_one_is_tracked(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.get("/api/repositories")).json() == []
