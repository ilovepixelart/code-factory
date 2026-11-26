"""The ticket changes the web app makes, through the HTTP API over the `board` sample."""

import httpx
import pytest
from fastapi import FastAPI

JSON = {"content-type": "application/json"}


@pytest.fixture
async def ids(app: FastAPI, board_ids: dict[str, str]) -> dict[str, str]:  # noqa: ARG001  # the app starts first
    return board_ids


def _path(ids: dict[str, str], title: str, repository: str = "sample", tail: str = "") -> str:
    return f"/api/tickets/{repository}/{ids[title]}{tail}"


async def _column(client: httpx.AsyncClient, ticket_id: str) -> str:
    page = (await client.get("/api/board")).json()["columns"]
    return next(name for name, cards in page.items() for c in cards if c["id"] == ticket_id)


async def test_a_created_ticket_is_filed_in_spec_and_answers_its_id(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    response = await client.post(
        "/api/tickets",
        json={"repository": "sample", "title": "New work", "type": "bug", "labels": "a, b"},
    )

    body = response.json()
    assert (response.status_code, body["notice"], body["undo"]) == (201, "", None)
    page = (await client.get(f"/api/tickets/sample/{body['id']}")).json()
    assert (page["ticket"]["title"], page["ticket"]["labels"], page["current_stage"]) == (
        "New work",
        "a, b",
        "spec",
    )
    assert body["id"] not in ids.values()


@pytest.mark.parametrize(
    ("fields", "error"),
    [
        ({"title": "x", "type": "epic"}, "unknown type epic"),
        ({"title": "x", "priority": "soon"}, "unknown priority soon"),
        ({"title": "x", "stage": "build"}, "a new ticket starts in Spec"),
        ({"title": "x", "archived": "maybe"}, "bad archived maybe"),
        ({"title": "  "}, "a ticket needs a title"),
    ],
)
async def test_a_create_that_breaks_a_rule_is_refused_with_the_sentence(
    client: httpx.AsyncClient,
    ids: dict[str, str],  # noqa: ARG001  # the sample holds tickets in `sample`
    fields: dict[str, object],
    error: str,
) -> None:
    response = await client.post("/api/tickets", json={"repository": "sample", **fields})
    assert (response.status_code, response.json()["detail"]) == (400, error)


@pytest.mark.parametrize(
    ("fields", "pointer"),
    [({"title": "x", "nope": "1"}, "/body/nope"), ({"title": 3}, "/body/title")],
)
async def test_a_create_field_unknown_or_of_the_wrong_kind_points_at_it(
    client: httpx.AsyncClient, fields: dict[str, object], pointer: str
) -> None:
    response = await client.post("/api/tickets", json={"repository": "sample", **fields})
    assert response.status_code == 400
    assert [e["pointer"] for e in response.json()["errors"]] == [pointer]


async def test_an_edit_changes_the_named_fields_and_leaves_the_rest(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    path = _path(ids, "Specs written")
    response = await client.patch(path, json={"title": "Renamed", "priority": "high"})

    assert response.json() == {"notice": "", "undo": None}
    ticket = (await client.get(path)).json()["ticket"]
    assert (ticket["title"], ticket["priority"], ticket["labels"]) == ("Renamed", "high", "docs")


async def test_an_edit_in_another_repository_finds_no_ticket(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    response = await client.patch(_path(ids, "Specs written", "second"), json={"title": "x"})
    assert (response.status_code, response.json()["detail"]) == (404, "no such ticket")


async def test_archiving_and_restoring_answer_with_their_notice(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    ticket_id = ids["Specs written"]
    path = _path(ids, "Specs written")

    archived = await client.patch(path, json={"archived": "true"})
    on_board = [
        c["id"] for cs in (await client.get("/api/board")).json()["columns"].values() for c in cs
    ]
    restored = await client.patch(path, json={"archived": ""})

    assert archived.json()["notice"] == f"Archived {ticket_id}"
    assert ticket_id not in on_board
    assert restored.json()["notice"] == f"Restored {ticket_id}"
    assert await _column(client, ticket_id) == "spec"


async def test_moving_to_build_without_a_branch_is_refused_with_how_to_get_one(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    ticket_id = ids["Specs written"]

    refused = await client.post(
        _path(ids, "Specs written", tail="/move"), json={"stage": "build", "order": []}
    )

    assert refused.status_code == 400
    assert refused.json()["detail"] == (
        f"{ticket_id} needs a branch before Build: start an agent on it, or run"
        f" code-factory start {ticket_id}"
    )
    assert await _column(client, ticket_id) == "spec"


async def test_moving_to_review_is_refused_until_a_pull_request_opens(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    response = await client.post(
        _path(ids, "A bug in flight", tail="/move"), json={"stage": "review", "order": []}
    )
    assert response.status_code == 400
    assert response.json()["detail"].endswith("before Review")


async def test_a_drop_ranks_the_column_in_the_order_given(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    first, third = ids["Specs written"], ids["Worked on main"]
    order = [f"sample/{third}", f"sample/{first}"]

    await client.post(
        _path(ids, "Specs written", tail="/move"), json={"stage": "spec", "order": order}
    )

    spec = (await client.get("/api/board")).json()["columns"]["spec"]
    assert [c["id"] for c in spec if c["repository"] == "sample"] == [third, first]


async def test_bulk_changes_every_ticket_with_one_notice(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    keys = [f"sample/{ids['Specs written']}", f"second/{ids['Elsewhere']}"]

    response = await client.post("/api/tickets/bulk", json={"tickets": keys, "priority": "low"})

    assert response.json()["notice"] == "Set low priority on 2 tickets"
    for title, repository in (("Specs written", "sample"), ("Elsewhere", "second")):
        page = (await client.get(_path(ids, title, repository))).json()
        assert page["ticket"]["priority"] == "low"


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"tickets": ["sample/x"]}, "one action and at least one ticket"),
        (
            {"priority": "low", "label": "a", "tickets": ["sample/x"]},
            "one action and at least one ticket",
        ),
        ({"priority": "low", "tickets": []}, "one action and at least one ticket"),
        ({"priority": "soon", "tickets": ["sample/CF-1"]}, "unknown priority soon"),
    ],
)
async def test_a_bulk_that_breaks_a_rule_is_refused(
    client: httpx.AsyncClient, ids: dict[str, str], body: dict[str, object], error: str
) -> None:
    del ids
    response = await client.post("/api/tickets/bulk", json=body)
    assert (response.status_code, response.json()["detail"]) == (400, error)


async def test_a_bulk_with_an_unknown_ticket_changes_none_of_them(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    keys = [f"sample/{ids['Specs written']}", "sample/CF-999999"]
    response = await client.post("/api/tickets/bulk", json={"tickets": keys, "priority": "low"})
    page = (await client.get(_path(ids, "Specs written"))).json()
    assert response.status_code == 404
    assert page["ticket"]["priority"] == ""


async def test_a_duplicate_copies_the_content_but_not_the_branch_or_the_links(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    response = await client.post(_path(ids, "A bug in flight", tail="/duplicate"))

    copy = (await client.get(f"/api/tickets/sample/{response.json()['id']}")).json()
    assert response.status_code == 201
    assert copy["ticket"]["title"] == "A bug in flight (copy)"
    assert (copy["ticket"]["type"], copy["ticket"]["priority"], copy["ticket"]["labels"]) == (
        "bug",
        "high",
        "ui, agents",
    )
    assert (copy["ticket"]["branch"], copy["ticket"]["parent"], copy["current_stage"]) == (
        "",
        "",
        "spec",
    )


async def test_linking_and_unlinking_a_blocker_shows_on_the_page(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    path = _path(ids, "Specs written", tail="/links")
    blocker = ids["Merged already"]
    link = {"kind": "blocked_by", "target": blocker}

    assert (await client.post(path, json=link)).status_code == 200
    linked = (await client.get(_path(ids, "Specs written"))).json()["ticket"]["blocked_by"]
    removed = await client.delete(f"{path}/blocked_by/{blocker}")
    unlinked = (await client.get(_path(ids, "Specs written"))).json()["ticket"]["blocked_by"]

    assert (linked, unlinked) == (blocker, "")
    assert removed.status_code == 200


async def test_a_link_to_a_ticket_that_does_not_exist_is_refused(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    response = await client.post(
        _path(ids, "Specs written", tail="/links"),
        json={"kind": "blocked_by", "target": "CF-999999"},
    )
    assert (response.status_code, response.json()["detail"]) == (
        400,
        "no ticket CF-999999",
    )


async def test_a_create_with_a_bad_branch_files_nothing(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    del ids
    before = len((await client.get("/api/board")).json()["columns"]["spec"])

    refused = await client.post(
        "/api/tickets", json={"repository": "sample", "title": "x", "branch": "bad branch"}
    )

    after = len((await client.get("/api/board")).json()["columns"]["spec"])
    assert refused.status_code == 400
    assert after == before


async def test_an_edit_with_a_bad_branch_changes_no_field(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    path = _path(ids, "Specs written")
    refused = await client.patch(path, json={"title": "Renamed", "branch": "bad branch"})
    assert refused.status_code == 400
    assert (await client.get(path)).json()["ticket"]["title"] == "Specs written"


async def test_an_edit_that_moves_to_review_changes_no_field(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    path = _path(ids, "Specs written")
    refused = await client.patch(path, json={"title": "Renamed", "stage": "review"})
    assert refused.status_code == 400
    assert (await client.get(path)).json()["ticket"]["title"] == "Specs written"


@pytest.mark.parametrize(
    ("tickets", "pointer"),
    [
        (None, "/body/tickets"),
        (3, "/body/tickets"),
        ("sample/CF-1", "/body/tickets"),
        ([3], "/body/tickets/0"),
    ],
)
async def test_a_bulk_whose_ticket_list_is_not_a_list_of_keys_points_at_it(
    client: httpx.AsyncClient, tickets: object, pointer: str
) -> None:
    response = await client.post("/api/tickets/bulk", json={"tickets": tickets, "priority": "low"})
    assert response.status_code == 400
    assert [e["pointer"] for e in response.json()["errors"]] == [pointer]


async def test_the_requirements_table_is_rendered_as_a_table(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    page = (await client.get(_path(ids, "Specs written"))).json()
    requirements = next(d for d in page["documents"] if d["stage"] == "requirements")
    assert "<table>" in requirements["html"]
    assert "<td>review</td>" in requirements["html"]


async def test_a_link_to_a_ticket_of_another_repository_is_refused(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    response = await client.post(
        _path(ids, "Specs written", tail="/links"),
        json={"kind": "blocked_by", "target": ids["Elsewhere"]},
    )
    assert (response.status_code, response.json()["detail"]) == (
        400,
        f"no ticket {ids['Elsewhere']}",
    )


async def test_a_huge_budget_does_not_break_the_board(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    await client.patch(_path(ids, "Specs written"), json={"budget": "9" * 400})
    board = await client.get("/api/board")
    page = await client.get(_path(ids, "Specs written"))
    assert (board.status_code, page.status_code) == (200, 200)
    assert page.json()["budget"] is None


async def test_the_archive_tabs_filter_how_a_ticket_left_the_board(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    del ids
    everything = (await client.get("/api/archive")).json()
    hand = (await client.get("/api/archive?show=hand")).json()
    released = (await client.get("/api/archive?show=released")).json()
    assert [r["title"] for r in everything["rows"]] == ["Archived"]
    assert [r["title"] for r in hand["rows"]] == ["Archived"]
    assert released["rows"] == []


async def test_the_archive_sorts_by_repository(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    await client.patch(_path(ids, "Elsewhere", "second"), json={"archived": "true"})
    rows = (await client.get("/api/archive?sort=repository&dir=asc")).json()
    assert [r["repository"] for r in rows["rows"]] == ["sample", "second"]


async def test_a_ticket_pages_tag_holds_until_the_ticket_changes(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    path = _path(ids, "Specs written")

    first = (await client.get(path)).headers["etag"]
    again = (await client.get(path)).headers["etag"]
    await client.patch(path, json={"priority": "high"})
    changed = (await client.get(path)).headers["etag"]

    assert first == again
    assert changed != first


async def test_an_edit_against_the_page_as_read_applies(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    path = _path(ids, "Specs written")
    tag = (await client.get(path)).headers["etag"]

    response = await client.patch(path, json={"title": "Renamed"}, headers={"If-Match": tag})

    assert response.status_code == 200
    assert (await client.get(path)).json()["ticket"]["title"] == "Renamed"


async def test_an_edit_against_a_page_changed_since_is_refused_and_changes_nothing(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    path = _path(ids, "Specs written")
    tag = (await client.get(path)).headers["etag"]
    await client.patch(path, json={"priority": "high"})

    response = await client.patch(path, json={"title": "Lost"}, headers={"If-Match": tag})

    assert response.status_code == 412
    assert response.json()["detail"] == (
        f"{ids['Specs written']} changed since it was read: read it again and redo the edit"
    )
    assert (await client.get(path)).json()["ticket"]["title"] == "Specs written"
