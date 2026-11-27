"""A read asks each source only what it needs, and asks it once."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast, override

import pytest
from fastapi import FastAPI

from board_fakes import FakeChecks
from code_factory.board.models import CheckRecord
from code_factory.board.module import board_sources
from code_factory.board.service import BoardService, BoardSources
from code_factory.platform.db import UnitOfWork
from code_factory.platform.services import Services
from code_factory.tickets.models import ActivityEntry, NewActivity, Ticket
from code_factory.tickets.service import ActivityService

NOW = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)


class CountingChecks(FakeChecks):
    def __init__(self) -> None:
        super().__init__()
        self.heads: list[dict[str, str] | None] = []
        self.attempts: list[str] = []

    @override
    async def latest_checks(
        self, ticket_ids: Sequence[str], *, heads: dict[str, str] | None = None
    ) -> dict[str, list[CheckRecord]]:
        self.heads.append(heads)
        return await super().latest_checks(ticket_ids, heads=heads)

    @override
    async def latest_attempt(self, ticket: str) -> CheckRecord | None:
        self.attempts.append(ticket)
        return await super().latest_attempt(ticket)


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
    assert checks.heads == [{bug: ""}]
    assert checks.attempts == [bug]


async def test_the_page_keeps_old_evidence_and_pairs_a_run_across_the_feed_boundary(
    sources: BoardSources,
    uow: UnitOfWork,
    board_ids: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bug = board_ids["A bug in flight"]
    recent = datetime(2040, 1, 1, tzinfo=UTC)
    earlier = NOW - timedelta(days=1)
    activity = sources.activity
    await activity.append(
        bug, NewActivity(kind="capture", data={"tree": "old-tree"}, at=earlier), by="alex"
    )
    await activity.append(
        bug,
        NewActivity(kind="capture_approved", data={"tree": "old-tree"}, at=earlier),
        by="alex",
    )
    await activity.append(
        bug,
        NewActivity(
            kind="capture_changes", data={"tree": "old-tree", "reason": "tighten"}, at=earlier
        ),
        by="alex",
    )
    await activity.append(
        bug,
        NewActivity(kind="checks", data={"commit": "old", "exit_code": 0}, at=earlier),
        by="check",
    )
    await activity.append(
        bug, NewActivity(kind="checks", data={"commit": "attempt"}, at=earlier), by="check"
    )
    for index in range(110):
        await activity.append(
            bug,
            NewActivity(
                kind="note", data={"text": f"note {index}"}, at=recent + timedelta(seconds=index)
            ),
            by="alex",
        )
    # The finish has an older timestamp and falls outside the visible activity window.
    await activity.append(
        bug,
        NewActivity(kind="run.ended", data={"run": "r", "exit_code": 0}, at=earlier),
        by="run:r",
    )
    await activity.append(
        bug,
        NewActivity(kind="run.started", data={"run": "r"}, at=recent + timedelta(minutes=2)),
        by="run:r",
    )
    unbounded_reads: list[str] = []
    original = ActivityService.entries

    async def trace(service: ActivityService, ticket: str) -> list[ActivityEntry]:
        unbounded_reads.append(ticket)
        return await original(service, ticket)

    monkeypatch.setattr(ActivityService, "entries", trace)
    page = await served(sources, uow).ticket_page("sample", bug)
    assert page["summary"]["capture"] == {"tree": "old-tree", "approved": True}
    assert page["status"]["capture"]["state"] == "sent_back"
    assert page["summary"]["gate"]["commit"] == "attempt"
    assert page["check"]["exit_code"] == -1
    assert page["card"]["check"] == {"passed": True, "commit": "old"}
    assert page["columns"]["build"] is not None
    assert len(page["activity"]) == 100
    assert (page["activity"][0]["run"], page["activity"][0]["outcome"]) == ("r", "finished")
    assert page["activity"][-1]["text"] == "note 11"
    assert unbounded_reads == []


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
