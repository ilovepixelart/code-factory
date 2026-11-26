"""A read asks each source only what it needs, and asks it once."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast, override

import pytest
from fastapi import FastAPI

from board_fakes import FakeChecks
from code_factory.board.models import CheckRecord
from code_factory.board.module import board_sources
from code_factory.board.service import BoardService, BoardSources
from code_factory.platform.db import UnitOfWork
from code_factory.platform.services import Services
from code_factory.tickets.models import Ticket

NOW = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)


class CountingChecks(FakeChecks):
    def __init__(self) -> None:
        super().__init__()
        self.asked: list[list[str]] = []

    @override
    async def latest_checks(self, ticket_ids: Sequence[str]) -> dict[str, list[CheckRecord]]:
        self.asked.append(list(ticket_ids))
        return await super().latest_checks(ticket_ids)


class CountingStages:
    def __init__(self, real: Any) -> None:  # noqa: ANN401
        self._real = real
        self.assessed = 0
        self.ids: set[str] = set()

    async def assess_tickets(self, tickets: Sequence[Ticket]) -> Any:  # noqa: ANN401
        self.assessed += 1
        self.ids = {ticket.id for ticket in tickets}
        return await self._real.assess_tickets(tickets)


@pytest.fixture
def sources(app: FastAPI) -> BoardSources:
    return board_sources(cast("Services", app.state.services))


def served(sources: BoardSources, uow: UnitOfWork, **ports: Any) -> BoardService:  # noqa: ANN401
    return BoardService(replace(sources, **ports), uow, clock=lambda: NOW)


async def test_the_page_reads_the_ticket_checks_once(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    bug = board_ids["A bug in flight"]
    checks = CountingChecks()
    await served(sources, uow, checks=checks).ticket_page("sample", bug)
    assert checks.asked == [[bug]]


async def test_the_ticket_page_does_not_assess_an_unrelated_repository(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    bug = board_ids["A bug in flight"]
    stages = CountingStages(sources.stages)
    page = await served(sources, uow, stages=stages).ticket_page("sample", bug)
    assert stages.assessed == 1
    assert stages.ids == set(page["titles"])
    assert board_ids["Elsewhere"] not in stages.ids


@pytest.mark.usefixtures("board_ids")
async def test_the_repository_list_needs_no_stage_assessment(
    sources: BoardSources, uow: UnitOfWork
) -> None:
    stages = CountingStages(sources.stages)
    names = await served(sources, uow, stages=stages).repositories()
    assert (names, stages.assessed) == (["sample", "second"], 0)


async def test_the_evidence_summary_needs_no_stage_assessment(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    stages = CountingStages(sources.stages)
    summary = await served(sources, uow, stages=stages).evidence_summary(board_ids["Archived"])
    assert (summary["verdict"], stages.assessed) == ("", 0)
