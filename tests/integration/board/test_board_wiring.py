"""The service feeds the rules real facts: what each module answers shows in the card and page.

The stages, sessions and releases answers are set by the test; the rules have their own tests.
"""

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from fastapi import FastAPI

from board_fakes import FakeRuns
from code_factory.board.module import board_sources
from code_factory.board.service import BoardService, BoardSources
from code_factory.platform.db import UnitOfWork
from code_factory.platform.services import Services
from code_factory.releases.models import ReleaseNaming
from code_factory.sessions.models import AtWork, SessionState, SessionView
from code_factory.stages.models import EvidenceItem, StageAssessment
from code_factory.talk.models import Choice
from code_factory.talk.service import TalkService
from code_factory.tickets.models import Review, Ticket
from code_factory.tickets.service import ReviewService

NOW = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)
PUBLISHED = datetime(2026, 11, 20, 8, 0, tzinfo=UTC)
ITEM = EvidenceItem(stage="build", required=True, present=True, detail="gate held")


class Stages:
    """The real assessments, with some replaced by what the test sets."""

    def __init__(self, real: Any, **changes: dict[str, Any]) -> None:  # noqa: ANN401
        self._real = real
        self._changes = changes

    async def assess_tickets(self, tickets: Sequence[Ticket]) -> dict[str, StageAssessment]:
        found = await self._real.assess_tickets(tickets)
        return {
            i: a.model_copy(update=self._changes.get(i, {})) if i in self._changes else a
            for i, a in found.items()
        }


class Sessions:
    """Live sessions and subagents as the test sets them."""

    def __init__(self, views: list[SessionView], at_work: list[AtWork]) -> None:
        self._views = views
        self._at_work = at_work

    async def board_views(self, _now: float) -> list[SessionView]:
        return self._views

    async def subagents_at_work(self, _now: float, *, fresh_only: bool) -> list[AtWork]:
        assert fresh_only
        return self._at_work


class Releases:
    """Which release named which ticket."""

    def __init__(self, named: dict[tuple[str, str], ReleaseNaming]) -> None:
        self._named = named

    async def naming(self, refs: list[tuple[str, str]]) -> dict[tuple[str, str], ReleaseNaming]:
        return {r: self._named[r] for r in refs if r in self._named}


@pytest.fixture
def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


@pytest.fixture
def sources(services: Services) -> BoardSources:
    return board_sources(services)


def served(sources: BoardSources, uow: UnitOfWork, **ports: Any) -> BoardService:  # noqa: ANN401
    return BoardService(replace(sources, **ports), uow, clock=lambda: NOW)


async def test_the_page_carries_the_stage_assessments_work_done_and_checklist(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    bug = board_ids["A bug in flight"]
    stages = Stages(sources.stages, **{bug: {"work_done": True, "checklist": [ITEM]}})
    page = await served(sources, uow, stages=stages).ticket_page("sample", bug)
    assert page["work_done"] is True
    assert page["checklist"] == [ITEM.model_dump()]


async def test_the_page_fields_carry_the_stage_the_ticket_declares(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    bug = board_ids["A bug in flight"]
    stages = Stages(sources.stages, **{bug: {"declared": "review"}})
    page = await served(sources, uow, stages=stages).ticket_page("sample", bug)
    assert page["ticket"]["stage"] == "review"
    assert page["card"]["declared"] == "review"


async def test_the_card_carries_the_stage_assessments_hold(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    bug = board_ids["A bug in flight"]
    stages = Stages(sources.stages, **{bug: {"hold": {"reason": "waits for review"}}})
    cards = json.loads((await served(sources, uow, stages=stages).board()).body)["columns"]["build"]
    assert cards[0]["hold"] == {"reason": "waits for review"}


async def test_the_page_summary_carries_the_latest_review_verdict(
    sources: BoardSources, services: Services, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    bug = board_ids["A bug in flight"]
    await services.get(ReviewService).submit_review(
        bug, Review(verdict="pass", summary="looks right"), by="reviewer"
    )
    page = await served(sources, uow).ticket_page("sample", bug)
    assert page["summary"]["verdict"] == "pass"


async def test_a_withdrawn_question_is_not_on_the_page(
    sources: BoardSources, services: Services, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    bug = board_ids["A bug in flight"]
    talk = services.get(TalkService)
    kept = await talk.ask(
        bug, "Which colour?", [Choice(text="red"), Choice(text="blue")], by="run:1"
    )
    dropped = await talk.ask(
        bug, "Which size?", [Choice(text="big"), Choice(text="small")], by="run:1"
    )
    await talk.withdraw(dropped.question_id, by="run:1")
    page = await served(sources, uow).ticket_page("sample", bug)
    assert [q["text"] for q in page["questions"]] == ["Which colour?"]
    assert kept.created


async def test_the_card_names_the_sessions_in_its_worktree_and_the_subagents_at_work(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    bug, other = board_ids["A bug in flight"], board_ids["Specs written"]
    views = [
        SessionView(
            session_id="s-1",
            cwd=f"/work/.code-factory/worktrees/{bug}",
            state=SessionState.WORKING,
            last_event_at=NOW.timestamp(),
        ),
        SessionView(
            session_id="s-2",
            cwd="/elsewhere",
            state=SessionState.IDLE,
            last_event_at=NOW.timestamp(),
        ),
    ]
    helper = AtWork(
        ticket=bug,
        session_id="s-1",
        agent_id="a-1",
        name="explorer",
        kind="session",
        doing="reading",
        since=1.0,
        last_event_at=2.0,
    )
    service = served(sources, uow, sessions=Sessions(views, [helper]))
    columns = json.loads((await service.board()).body)["columns"]
    card = columns["build"][0]
    assert card["sessions"] == [{"session_id": "s-1", "state": "working"}]
    assert card["subagents"] == [helper.model_dump()]
    spec = {c["id"]: c for c in columns["spec"]}
    assert (spec[other]["sessions"], spec[other]["subagents"]) == ([], [])


async def test_a_released_ticket_has_no_card_and_the_archive_names_its_release(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    gone = board_ids["Merged already"]
    stages = Stages(sources.stages, **{gone: {"stage": "released"}})
    named = {("sample", gone): ReleaseNaming(version="0.3.0", published_at=PUBLISHED)}
    runs = FakeRuns()
    service = served(sources, uow, stages=stages, releases=Releases(named), runs=runs)
    columns = json.loads((await service.board()).body)["columns"]
    assert gone not in {c["id"] for cards in columns.values() for c in cards}
    assert gone not in runs.asked
    rows = (await service.archive({"q": gone}))["rows"]
    assert [(r["id"], r["stage"], r["release"], r["archived_at"]) for r in rows] == [
        (gone, "released", "0.3.0", PUBLISHED.timestamp())
    ]
