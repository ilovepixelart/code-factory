"""The Memory page and the owner's changes to it, through the HTTP API over the `board` sample."""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from code_factory.memory.models import NewMemory
from code_factory.memory.service import MemoryService

RULE = "Keep it small and test first"


@pytest.fixture(autouse=True)
async def _sample(app: FastAPI, board_ids: dict[str, str]) -> None:
    """The `board` sample, in place before the test runs."""


async def _page(client: httpx.AsyncClient, query: str = "") -> dict[str, Any]:
    return (await client.get(f"/api/memory{query}")).json()


def _ids(records: list[dict[str, Any]]) -> list[str]:
    return [r["id"] for r in records]


async def test_entries_nobody_reviewed_are_listed_for_review_with_the_repositories(
    client: httpx.AsyncClient,
) -> None:
    page = await _page(client)
    statements = sorted(r["statement"] for r in page["unreviewed"])
    assert statements == [RULE, "Ship small pull requests", "The gate ran twice on one tree"]
    assert (page["rules"], page["decisions"], page["lessons"], page["retired"]) == ([], [], [], [])
    assert {"sample", "second"} <= set(page["repositories"])


async def test_a_created_entry_is_read_back_where_location_points(
    client: httpx.AsyncClient,
) -> None:
    body = {
        "repository": "sample",
        "kind": "rule",
        "statement": "Read the caller",
        "source": "CF-9",
    }

    created = await client.post("/api/memory", json=body)
    read = await client.get(created.headers["location"])

    assert created.status_code == 201
    assert created.headers["location"] == f"/api/memory/sample/{created.json()['id']}"
    listed = next(r for r in (await _page(client))["unreviewed"] if r["id"] == read.json()["id"])
    assert (read.status_code, read.json()) == (200, listed)
    assert listed["statement"] == "Read the caller"


async def test_an_entry_that_does_not_exist_reads_as_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/memory/sample/no-such-entry")).status_code == 404


async def test_an_edit_marks_the_entry_reviewed_and_files_it_under_its_kind(
    client: httpx.AsyncClient,
) -> None:
    rule = next(r for r in (await _page(client))["unreviewed"] if r["statement"] == RULE)

    response = await client.patch(f"/api/memory/sample/{rule['id']}", json={})

    page = await _page(client)
    assert response.json() == {"notice": "", "undo": None}
    assert _ids(page["rules"]) == [rule["id"]]
    assert rule["id"] not in _ids(page["unreviewed"])


async def test_an_entry_added_by_the_owner_appears_with_its_text(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/memory",
        json={
            "repository": "sample",
            "kind": "lesson",
            "statement": "Check the log first",
            "why": "It names the cause",
            "source": "CF-9",
            "guard": "",
        },
    )

    page = await _page(client)
    added = next(r for r in page["unreviewed"] if r["statement"] == "Check the log first")
    assert response.status_code == 201
    assert (added["kind"], added["why"], added["source"]) == (
        "lesson",
        "It names the cause",
        "CF-9",
    )


async def test_an_entry_the_service_refuses_answers_its_sentence(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/memory", json={"repository": "sample", "kind": "rule", "statement": "  "}
    )
    assert response.status_code == 400
    assert response.json()["detail"]


async def test_retiring_moves_an_entry_to_history_with_its_reason(
    client: httpx.AsyncClient,
) -> None:
    rule = next(r for r in (await _page(client))["unreviewed"] if r["statement"] == RULE)
    await client.patch(f"/api/memory/sample/{rule['id']}", json={})

    response = await client.post(
        f"/api/memory/sample/{rule['id']}/retire", json={"reason": "no longer true"}
    )

    page = await _page(client)
    assert response.status_code == 200
    assert [(r["id"], r["retired"]) for r in page["retired"]] == [(rule["id"], "no longer true")]
    assert rule["id"] not in _ids(page["rules"])


async def test_retiring_without_a_reason_is_refused(client: httpx.AsyncClient) -> None:
    rule = next(r for r in (await _page(client))["unreviewed"] if r["statement"] == RULE)
    response = await client.post(f"/api/memory/sample/{rule['id']}/retire", json={"reason": ""})
    assert (response.status_code, response.json()["detail"]) == (
        400,
        "say in one line why it no longer applies",
    )


async def test_a_proposal_waits_for_approval_and_dismissing_it_files_it_as_history(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    memory = app.state.services.get(MemoryService)
    new = NewMemory(repository="sample", kind="rule", statement="Name the test first", source="run")
    proposed = await memory.propose(new, by="run:1")

    before = await _page(client)
    response = await client.post(f"/api/memory/sample/{proposed.id}/dismiss")
    after = await _page(client)

    assert proposed.id in _ids(before["unreviewed"])
    assert response.status_code == 200
    assert proposed.id not in _ids(after["unreviewed"])
    assert proposed.id in _ids(after["retired"])


async def test_searching_lists_the_entries_that_hold_every_word(client: httpx.AsyncClient) -> None:
    page = await _page(client, "?q=gate+twice")
    assert page["matched"] == 1
    assert [r["snippet"] for r in page["results"]] == ["The gate ran twice on one tree"]


async def test_merging_an_entry_into_itself_is_refused(client: httpx.AsyncClient) -> None:
    rule = next(r for r in (await _page(client))["unreviewed"] if r["statement"] == RULE)
    await client.patch(f"/api/memory/sample/{rule['id']}", json={})
    response = await client.post(
        f"/api/memory/sample/{rule['id']}/merge", json={"into": rule["id"]}
    )
    assert (response.status_code, response.json()["detail"]) == (
        400,
        "an entry cannot be merged into itself; name another entry",
    )


async def test_search_answers_the_page_and_size_it_used(client: httpx.AsyncClient) -> None:
    page = await _page(client, "?q=the&page=9&size=2")
    assert (page["page"], page["size"]) == (1, 2)


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({"repository": "sample", "kind": "rule"}, "statement"),
        ({"repository": "sample", "kind": "poem", "statement": "x"}, "kind"),
    ],
)
async def test_an_entry_the_models_refuse_is_a_400_naming_the_field(
    client: httpx.AsyncClient, body: dict[str, str], fragment: str
) -> None:
    response = await client.post("/api/memory", json=body)
    assert response.status_code == 400
    assert fragment in response.json()["detail"]


async def test_the_meter_counts_only_what_every_session_loads(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/memory",
        json={"repository": "sample", "kind": "rule", "statement": "x" * 500, "scope": "build"},
    )
    page = await _page(client)
    every = [r for r in page["unreviewed"] if r["scope"] in ("", "core")]
    assert page["loaded_chars"] == sum(r["chars"] for r in every)


@pytest.mark.parametrize(
    ("method", "tail", "body", "pointer"),
    [
        (
            "POST",
            "",
            {"repository": "sample", "kind": "rule", "statement": "x", "why": None},
            "/body/why",
        ),
        ("POST", "", {"repository": "sample", "kind": "habit", "statement": "x"}, "/body/kind"),
        ("PATCH", "/sample/any", {"title": "x"}, "/body/title"),
        ("POST", "/sample/any/merge", {}, "/body/into"),
        ("POST", "/sample/any/retire", {"reason": 3}, "/body/reason"),
    ],
)
async def test_a_memory_body_out_of_shape_points_at_the_field(
    client: httpx.AsyncClient, method: str, tail: str, body: dict[str, object], pointer: str
) -> None:
    response = await client.request(method, f"/api/memory{tail}", json=body)
    assert response.status_code == 400
    assert [e["pointer"] for e in response.json()["errors"]] == [pointer]
