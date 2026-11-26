"""Talk, review findings, undo and files of a ticket, through the HTTP API."""

from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI

from code_factory.platform.services import Services
from code_factory.sample.service import SampleService
from code_factory.talk.models import Choice
from code_factory.talk.service import TalkService
from code_factory.tickets.models import Finding, Review
from code_factory.tickets.service import DocumentService, ReviewService
from code_factory.undo.service import UndoService


@pytest.fixture
def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


@pytest.fixture
async def ids(services: Services) -> dict[str, str]:
    return await services.get(SampleService).load("board")


def _path(ids: dict[str, str], title: str, tail: str = "") -> str:
    return f"/api/tickets/sample/{ids[title]}{tail}"


async def _page(client: httpx.AsyncClient, ids: dict[str, str], title: str) -> dict[str, Any]:
    return (await client.get(_path(ids, title))).json()


async def test_an_open_question_is_listed_and_answering_it_records_the_owners_words(
    services: Services, client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    await services.get(TalkService).ask(
        ids["Specs written"], "Which colour?", [Choice(text="red"), Choice(text="blue")],
        document="spec", by="run:1",
    )  # fmt: skip
    asked = (await _page(client, ids, "Specs written"))["questions"]
    assert [(q["document"], q["text"], q["answer"]) for q in asked] == [
        ("spec.md", "Which colour?", "")
    ]

    response = await client.post(
        _path(ids, "Specs written", "/answers"),
        json={"document": "spec", "index": 0, "question": "Which colour?", "choices": ["blue"]},
    )

    answered = (await _page(client, ids, "Specs written"))["questions"]
    assert response.json() == {"notice": "", "undo": None}
    assert (answered[0]["answer"], answered[0]["answered_by"]) == ("blue", "http")


async def test_an_answer_to_a_question_that_changed_is_refused(
    services: Services, client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    await services.get(TalkService).ask(ids["Specs written"], "Which colour?", [], by="run:1")
    response = await client.post(
        _path(ids, "Specs written", "/answers"),
        json={"document": "spec", "index": 0, "question": "Something else?", "answer": "x"},
    )
    assert response.status_code in {400, 404, 409}
    assert response.json()["detail"]


async def test_a_message_and_a_comment_appear_in_the_activity_under_the_owner(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    await client.post(_path(ids, "Specs written", "/messages"), json={"text": "please start"})
    await client.post(_path(ids, "Specs written", "/comments"), json={"text": "looks right"})

    activity = (await _page(client, ids, "Specs written"))["activity"]

    said = {(a["kind"], a["text"]) for a in activity}
    assert {("message", "please start"), ("comment", "looks right")} <= said
    owned = {a["kind"]: a for a in activity if a["kind"] in {"message", "comment"}}
    assert {k: a["sentence"] for k, a in owned.items()} == {
        "message": "You sent a message",
        "comment": "You commented",
    }


async def test_a_findings_list_names_each_finding_and_closing_one_needs_a_reason(
    services: Services, client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    review = Review(
        verdict="changes",
        summary="one thing",
        findings=[Finding(severity="major", text="the guard is missing", path="a.py", line=3)],
    )
    await services.get(ReviewService).submit_review(ids["Specs written"], review, by="run:2")
    path = _path(ids, "Specs written", "/findings")

    listed = (await client.get(path)).json()["findings"]
    refused = await client.post(path + "/F1", json={"state": "fixed", "reason": ""})
    closed = await client.post(path + "/F1", json={"state": "fixed", "reason": "added the guard"})
    after = (await client.get(path)).json()["findings"]

    assert [(f["id"], f["severity"], f["class"], f["state"]) for f in listed] == [
        ("F1", "major", "important", "open")
    ]
    assert (refused.status_code, closed.status_code) == (400, 200)
    assert [(f["state"], f["reason"]) for f in after] == [("fixed", "added the guard")]


async def test_a_finding_that_does_not_exist_is_a_404(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    response = await client.post(
        _path(ids, "Specs written", "/findings/F9"), json={"state": "fixed", "reason": "x"}
    )
    assert response.status_code == 404


async def test_an_undo_runs_once_and_then_is_gone(
    services: Services, client: httpx.AsyncClient
) -> None:
    undone: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any], by: str) -> None:
        undone.append({**payload, "by": by})

    undo = services.get(UndoService)
    undo.register("test.route", handler)
    offered = await undo.offer("test.route", {"ticket": "CF-1"}, "Did it")

    first = await client.post(f"/api/undo/{offered.undo}")
    second = await client.post(f"/api/undo/{offered.undo}")

    assert (first.status_code, first.json()) == (200, {"notice": "", "undo": None})
    assert undone == [{"ticket": "CF-1", "by": "owner:owner"}]
    assert (second.status_code, second.json()["detail"]) == (410, "nothing to undo any more")


async def test_a_mock_image_is_served_with_its_content_type(
    services: Services, client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 8
    await services.get(DocumentService).put_mock_file(
        ids["A bug in flight"], "screen.png", png, by="owner:owner"
    )

    response = await client.get(_path(ids, "A bug in flight", "/mock/screen.png"))
    page = await _page(client, ids, "A bug in flight")

    assert (response.status_code, response.headers["content-type"], response.content) == (
        200,
        "image/png",
        png,
    )
    mock = next(d for d in page["documents"] if d["stage"] == "mock")
    assert mock["files"] == ["screen.png"]


async def test_the_diff_of_a_ticket_in_an_untracked_repository_is_empty(
    client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    response = await client.get(_path(ids, "A bug in flight", "/diff"))
    assert response.json() == {
        "files": [],
        "cut": False,
        "limit": 400,
        "branch": "ticket/cf-2",
        "default_branch": "",
    }


async def test_the_scorers_of_a_tracked_repository_are_listed_with_no_answers_yet(
    services: Services, client: httpx.AsyncClient, tmp_path: Path
) -> None:
    from code_factory.repositories.service import RepositoryService  # noqa: PLC0415

    root = tmp_path / "scored"
    (root / ".code-factory").mkdir(parents=True)
    (root / ".code-factory" / "config.toml").write_text(
        '[[scorers]]\nname = "tidy"\nquestion = "Did it stay small?"\nstage = "build"\n'
        "sample = 0.5\nthreshold = 3\n"
    )
    await services.get(RepositoryService).track(root)

    scorers = (await client.get("/api/scorers")).json()["scorers"]

    assert [(s["repository"], s["name"], s["question"], s["stage"]) for s in scorers] == [
        ("scored", "tidy", "Did it stay small?", "build")
    ]
    assert scorers[0]["week"] == {"yes": 0, "no": 0, "unclear": 0, "pass_rate": None}


async def test_a_repository_whose_mounts_cannot_be_judged_does_not_hide_the_others_scorers(
    services: Services,
    client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from code_factory.repositories.service import RepositoryService  # noqa: PLC0415
    from code_factory.settings.adapters import local_resolver  # noqa: PLC0415
    from code_factory.settings.service import checks as settings_checks  # noqa: PLC0415

    monkeypatch.setattr(
        settings_checks, "local_resolver", lambda roots: local_resolver(roots, deadline_s=0.0)
    )
    for name, body in (
        ("mounted", '[checks]\ncommand = "x"\ncontainer_mounts = ["/srv/a:/x"]\n'),
        ("scored", '[[scorers]]\nname = "tidy"\nquestion = "Q?"\nstage = "build"\n'),
    ):
        root = tmp_path / name
        (root / ".code-factory").mkdir(parents=True)
        (root / ".code-factory" / "config.toml").write_text(body)
        await services.get(RepositoryService).track(root)

    response = await client.get("/api/scorers")

    assert response.status_code == 200
    assert [s["repository"] for s in response.json()["scorers"]] == ["scored"]


async def test_a_finding_is_not_closed_with_a_reason_that_is_not_text(
    services: Services, client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    review = Review(verdict="changes", summary="x", findings=[Finding(severity="major", text="t")])
    await services.get(ReviewService).submit_review(ids["Specs written"], review, by="run:2")
    response = await client.post(
        _path(ids, "Specs written", "/findings/F1"), json={"state": "fixed", "reason": None}
    )
    assert response.status_code == 400
    assert [e["pointer"] for e in response.json()["errors"]] == ["/body/reason"]


async def test_the_answered_choices_are_ticked_on_the_page(
    services: Services, client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    await services.get(TalkService).ask(
        ids["Specs written"], "Which?", [Choice(text="red"), Choice(text="blue")], by="run:1"
    )
    await client.post(
        _path(ids, "Specs written", "/answers"),
        json={"document": "", "index": 0, "question": "Which?", "choices": ["blue"]},
    )
    choices = (await _page(client, ids, "Specs written"))["questions"][0]["choices"]
    assert [(c["text"], c["ticked"]) for c in choices] == [("red", False), ("blue", True)]


async def test_a_coordinator_edit_in_the_activity_carries_what_undo_needs(
    services: Services, client: httpx.AsyncClient, ids: dict[str, str]
) -> None:
    from code_factory.tickets.models import TicketFields  # noqa: PLC0415
    from code_factory.tickets.service import CoordinatorService  # noqa: PLC0415

    await services.get(CoordinatorService).edit(
        ids["Specs written"], TicketFields(priority="high"), by="run:coordinator"
    )
    activity = (await _page(client, ids, "Specs written"))["activity"]
    edit = next(a["edit"] for a in activity if a["kind"] == "coordinator_edit")
    assert edit == {"name": "priority", "from": "", "to": "high"}


@pytest.mark.parametrize(
    ("tail", "body", "pointer"),
    [
        ("/messages", {"text": "hi", "urgent": True}, "/body/urgent"),
        ("/comments", {"text": "x", "line": "7"}, "/body/line"),
        ("/answers", {"document": "spec", "index": "0", "question": "Which?"}, "/body/index"),
        ("/coordinator-undo", {}, "/body/name"),
    ],
)
async def test_a_talk_body_out_of_shape_points_at_the_field(
    client: httpx.AsyncClient, ids: dict[str, str], tail: str, body: dict[str, object], pointer: str
) -> None:
    response = await client.post(_path(ids, "Specs written", tail), json=body)
    assert response.status_code == 400
    assert [e["pointer"] for e in response.json()["errors"]] == [pointer]
