"""The board service over the real tickets, stages, talk and timeline services.

The runs, checks, delivery and queue ports are the fakes in `tests/board_fakes.py`.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from fastapi import FastAPI

from board_fakes import FakeChecks, FakeDelivery, FakeLimits, FakeQueue, FakeRuns
from code_factory.board.models import (
    ActivityRecord,
    CheckRecord,
    PullFacts,
    RunCard,
    TicketRuns,
)
from code_factory.board.module import board_sources
from code_factory.board.service import BoardService, BoardSources
from code_factory.platform.db import UnitOfWork
from code_factory.platform.services import Services
from code_factory.talk.models import Choice
from code_factory.talk.service import TalkService
from code_factory.tickets.models import TicketFields
from code_factory.tickets.service import TicketService

NOW = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)


@pytest.fixture
def services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


@pytest.fixture
def sources(services: Services) -> BoardSources:
    return board_sources(services)


@pytest.fixture
def board(sources: BoardSources, uow: UnitOfWork) -> BoardService:
    return BoardService(sources, uow, clock=lambda: NOW)


def with_ports(sources: BoardSources, uow: UnitOfWork, **ports: Any) -> BoardService:  # noqa: ANN401
    return BoardService(replace(sources, **ports), uow, clock=lambda: NOW)


def columns_of(answer: dict[str, Any]) -> dict[str, list[str]]:
    return {name: [card["id"] for card in cards] for name, cards in answer["columns"].items()}


async def test_the_board_puts_each_open_ticket_in_its_column(
    board: BoardService, board_ids: dict[str, str]
) -> None:
    answer = json.loads((await board.board()).body)
    assert columns_of(answer) == {
        "spec": [
            board_ids["Specs written"],
            board_ids["Worked on main"],
            board_ids["Elsewhere"],
            board_ids["Other repository, second"],
        ],
        "build": [board_ids["A bug in flight"]],
        "review": [],
        "merged": [board_ids["Merged already"]],
    }
    assert answer["today"] == "2026-11-23"
    assert board_ids["Archived"] not in json.dumps(columns_of(answer))


async def test_the_etag_is_the_digest_of_the_body_and_follows_a_change(
    board: BoardService, tickets: TicketService, board_ids: dict[str, str]
) -> None:
    first = await board.board()
    again = await board.board()
    await tickets.update(board_ids["Specs written"], TicketFields(title="Renamed"), by="alex")
    changed = await board.board()
    assert first.etag == again.etag
    assert first.etag.startswith('"')
    assert changed.etag != first.etag
    assert "Renamed" in changed.body


async def test_an_open_question_shows_on_its_ticket_card(
    board: BoardService, services: Services, board_ids: dict[str, str]
) -> None:
    await services.get(TalkService).ask(
        board_ids["Specs written"],
        "Which colour?",
        [Choice(text="red"), Choice(text="blue")],
        by="run:1",
    )
    cards = json.loads((await board.board()).body)["columns"]["spec"]
    asked = {card["id"]: card["open_questions"] for card in cards}
    assert asked[board_ids["Specs written"]] == 1
    assert asked[board_ids["Worked on main"]] == 0


async def test_runs_and_their_spend_show_on_the_card(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    run = RunCard(
        id="aaaaaaaaaaaa",
        stage="build",
        iteration=2,
        loop=True,
        max_iterations=8,
        attempt=0,
        agent="",
        started_at=1790000500.0,
    )
    runs = FakeRuns({board_ids["A bug in flight"]: TicketRuns(runs=[run], spent=4.25)})
    service = with_ports(sources, uow, runs=runs)
    cards = json.loads((await service.board()).body)["columns"]["build"]
    assert cards[0]["spent"] == 4.25
    assert cards[0]["runs"] == [run.model_dump()]
    assert cards[0]["budget"] == 2.5


async def test_the_checks_and_the_pull_request_show_on_the_card(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    bug = board_ids["A bug in flight"]
    pull = PullFacts(
        state="open", head="abc1234", url="https://x/pull/2", review="approved", ci="failed"
    )
    service = with_ports(
        sources,
        uow,
        checks=FakeChecks(
            {
                bug: [
                    CheckRecord(commit="abc1234", exit_code=0),
                    CheckRecord(commit="old", exit_code=1),
                ]
            }
        ),
        delivery=FakeDelivery(
            {bug: pull}, {bug: [ActivityRecord(kind="pull_request", at=1789871400.0)]}
        ),
    )
    [card] = json.loads((await service.board()).body)["columns"]["build"]
    assert card["check"] == {"passed": True, "commit": "abc1234"}
    assert card["pull"]["review"] == "approved"
    assert card["delivery_event"] == {"kind": "pull_request", "at": 1789871400.0, "retry_at": None}


async def test_the_queue_and_the_holder_show_on_the_card(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    bug = board_ids["A bug in flight"]
    queue = FakeQueue({bug: "next, touches CF-9"}, {bug: "claude"})
    service = with_ports(sources, uow, queue=queue)
    [card] = json.loads((await service.board()).body)["columns"]["build"]
    assert (card["queue"], card["overlap"], card["holder"]) == ("next", "touches CF-9", "claude")


async def test_column_limits_are_the_boards_limits(sources: BoardSources, uow: UnitOfWork) -> None:
    service = with_ports(sources, uow, limits=FakeLimits({"spec": 2, "other": 3}))
    assert json.loads((await service.board()).body)["limits"] == {"spec": 2}


async def test_the_list_filters_cards_and_cuts_them_to_the_listed_fields(
    board: BoardService, board_ids: dict[str, str]
) -> None:
    answer = await board.tickets({"type": ["bug"]})
    assert columns_of(answer) == {
        "spec": [],
        "build": [board_ids["A bug in flight"]],
        "review": [],
        "merged": [],
    }
    assert len(answer["columns"]["build"][0]) == 20
    assert answer["problems"] == []


async def test_the_list_with_no_filter_has_every_open_card(
    board: BoardService, board_ids: dict[str, str]
) -> None:
    answer = await board.tickets({})
    assert sum(len(ids) for ids in columns_of(answer).values()) == 6
    assert board_ids["Archived"] not in json.dumps(columns_of(answer))


async def test_a_board_read_asks_the_sources_only_about_tickets_on_the_board(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    runs = FakeRuns()
    await with_ports(sources, uow, runs=runs).board()
    assert board_ids["Archived"] not in runs.asked
    assert sorted(runs.asked) == sorted(
        board_ids[t]
        for t in (
            "Specs written",
            "A bug in flight",
            "Worked on main",
            "Merged already",
            "Elsewhere",
            "Other repository, second",
        )
    )
