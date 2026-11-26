"""One ticket's page, the archive and the repository list over the real services."""

import json
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection

from board_fakes import FakeChecks, FakeRuns
from code_factory.board.models import CheckRecord, RunRecord
from code_factory.board.module import board_sources
from code_factory.board.service import BoardService, BoardSources
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.tickets.models import DocumentName, DocumentWrite, NewActivity, NewTicket
from code_factory.tickets.service import ActivityService, DocumentService, TicketService

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
# Reads, and the savepoints a unit of work wraps them in.
READS = ("SELECT", "WITH", "SAVEPOINT", "RELEASE", "ROLLBACK TO")
PAGE_KEYS = [
    "runs", "spent", "cost", "budget", "default_budget", "halted", "ticket", "repository",
    "work_done", "checklist", "summary", "current_stage", "questions", "documents", "plan", "link",
    "titles", "stages_by_id", "linked", "description_html", "check", "check_log",
    "checks_configured", "activity", "checking", "month_budget", "subagents", "card", "columns",
    "branch", "status",
]  # fmt: skip


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


@contextmanager
def recorded(connection: AsyncConnection) -> Generator[list[str]]:
    seen: list[str] = []

    def spy(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:  # noqa: ANN401
        seen.append(statement)

    event.listen(connection.sync_connection, "before_cursor_execute", spy)
    try:
        yield seen
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", spy)


async def test_the_page_has_the_keys_in_the_order_the_app_reads(
    board: BoardService, board_ids: dict[str, str]
) -> None:
    page = await board.ticket_page("sample", board_ids["A bug in flight"])
    assert list(page) == PAGE_KEYS


async def test_the_page_shows_the_ticket_its_documents_and_its_links(
    board: BoardService, board_ids: dict[str, str]
) -> None:
    bug, first, third = (
        board_ids[t] for t in ("A bug in flight", "Specs written", "Worked on main")
    )
    page = await board.ticket_page("sample", bug)
    assert page["ticket"]["labels"] == "ui, agents"
    assert page["repository"] == "sample"
    assert page["current_stage"] == "build"
    assert page["documents"] == [
        {"stage": "requirements", "html": None},
        {"stage": "mock", "html": None, "files": []},
        {"stage": "spec", "html": "<h1>Spec</h1>\n<p>Started.</p>\n"},
        {"stage": "uat", "html": None},
    ]
    assert page["link"]["parent"] == first
    assert page["link"]["blocks"] == [third]
    assert page["titles"][first] == "Specs written"
    assert page["stages_by_id"][bug] == "build"
    assert page["branch"] == "ticket/cf-2"
    assert page["card"]["id"] == bug
    assert page["description_html"].startswith("<p>A description long enough")


async def test_a_linked_ticket_names_its_own_repository_title_and_stage(
    board: BoardService, tickets: TicketService, board_ids: dict[str, str]
) -> None:
    bug, first = board_ids["A bug in flight"], board_ids["Specs written"]
    other = await tickets.create(
        NewTicket(repository="second", title="Waits on the bug", blocked_by=[bug]), by="alex"
    )
    page = await board.ticket_page("sample", bug)
    assert page["linked"][other.id] == {
        "repository": "second",
        "title": "Waits on the bug",
        "stage": "spec",
    }
    assert page["linked"][first] == {
        "repository": "sample",
        "title": "Specs written",
        "stage": page["stages_by_id"][first],
    }
    assert other.id not in page["titles"]


async def test_the_mock_is_listed_only_for_a_ui_ticket(
    board: BoardService, board_ids: dict[str, str]
) -> None:
    page = await board.ticket_page("sample", board_ids["Specs written"])
    assert [d["stage"] for d in page["documents"]] == ["requirements", "spec", "uat"]


async def test_a_ticket_with_no_run_and_no_check_has_empty_run_words(
    board: BoardService, board_ids: dict[str, str]
) -> None:
    page = await board.ticket_page("sample", board_ids["A bug in flight"])
    assert (page["runs"], page["spent"], page["halted"], page["check"], page["check_log"]) == (
        [],
        0,
        "",
        None,
        "",
    )
    assert (page["checking"], page["month_budget"], page["plan"]) == (False, None, None)
    assert page["status"] == {"conflict": None, "capture": None}


async def test_the_columns_count_the_seconds_in_those_entered_and_null_the_rest(
    board: BoardService, board_ids: dict[str, str]
) -> None:
    columns = (await board.ticket_page("sample", board_ids["A bug in flight"]))["columns"]
    assert (columns["spec"] is None, columns["build"] is None, columns["review"]) == (
        False,
        False,
        None,
    )


@pytest.mark.parametrize(("exit_code", "log_shown"), [(1, True), (0, False)])
async def test_the_log_is_read_only_when_the_latest_check_failed(
    sources: BoardSources,
    uow: UnitOfWork,
    board_ids: dict[str, str],
    exit_code: int,
    log_shown: bool,
) -> None:
    bug = board_ids["A bug in flight"]
    checks = FakeChecks({bug: [CheckRecord(commit="c1", exit_code=exit_code)]}, log="boom\n")
    page = await with_ports(sources, uow, checks=checks).ticket_page("sample", bug)
    assert page["check"]["exit_code"] == exit_code
    assert page["check_log"] == ("boom\n" if log_shown else "")
    assert checks.log_asked == ([(bug, 40)] if log_shown else [])


async def test_a_running_check_marks_the_ticket_checking(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    service = with_ports(sources, uow, checks=FakeChecks(running=True))
    page = await service.ticket_page("sample", board_ids["A bug in flight"])
    assert page["checking"] is True


@pytest.fixture
async def tracked(services: Services, tmp_path: Path) -> Path:
    root = tmp_path / "sample"
    (root / ".code-factory").mkdir(parents=True)
    (root / ".code-factory" / "config.toml").write_text(
        '[agents]\nbudget_usd = 5\nmonthly_budget_usd = 41\n\n[checks]\ncommand = "make test"\n'
    )
    await services.get(RepositoryService).track(root)
    return root


@pytest.mark.usefixtures("tracked")
async def test_the_month_budget_projects_the_day_it_runs_out(
    sources: BoardSources, uow: UnitOfWork, board_ids: dict[str, str]
) -> None:
    runs = FakeRuns(month_cost=21.0)
    service = with_ports(sources, uow, runs=runs)
    page = await service.ticket_page("sample", board_ids["A bug in flight"])
    assert page["month_budget"] == {
        "month": "2026-11",
        "spent": 21.0,
        "budget": 41.0,
        "runs_out": "2026-11-21",
        "reached": False,
    }
    assert runs.windows == [
        ("sample", datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 12, 1, tzinfo=UTC))
    ]
    assert (page["default_budget"], page["budget"], page["checks_configured"]) == (5.0, 2.5, True)


@pytest.mark.usefixtures("tracked")
async def test_the_repository_budget_stands_in_for_a_ticket_without_one(
    board: BoardService, board_ids: dict[str, str]
) -> None:
    page = await board.ticket_page("sample", board_ids["Worked on main"])
    assert (page["budget"], page["card"]["budget"]) == (5.0, 5.0)


@pytest.mark.usefixtures("tracked")
async def test_the_month_budget_of_a_repository_and_its_refusal(
    board: BoardService,
) -> None:
    answer = await board.month_budget("sample")
    assert answer is not None
    assert answer["budget"] == 41.0
    with pytest.raises(NotFoundError, match="unknown repository"):
        await board.month_budget("nowhere")


async def test_a_ticket_in_another_repository_or_none_is_no_such_ticket(
    board: BoardService, board_ids: dict[str, str]
) -> None:
    for repository, ticket in (("second", board_ids["A bug in flight"]), ("sample", "CF-999")):
        with pytest.raises(NotFoundError, match="no such ticket"):
            await board.ticket_page(repository, ticket)


async def test_an_archived_and_a_merged_ticket_still_have_a_page_and_a_card(
    board: BoardService, board_ids: dict[str, str]
) -> None:
    archived = await board.ticket_card("sample", board_ids["Archived"])
    merged = await board.ticket_page("sample", board_ids["Merged already"])
    assert archived is not None
    assert archived["archived"] is True
    assert merged["current_stage"] == "merged"
    assert await board.ticket_card("sample", "CF-999") is None


async def test_the_summary_names_what_only_a_review_checks(
    board: BoardService, services: Services, board_ids: dict[str, str]
) -> None:
    first = board_ids["Specs written"]
    text = (
        "# Requirements\n\n## Requirements\n\n"
        "| ID | Requirement | Named check |\n|---|---|---|\n"
        "| CF-1-R1 | It works | review |\n\n"
        "## Acceptance criteria\n\n| ID | Criterion | Check |\n|---|---|---|\n"
        "| A1 | It shows | review |\n| A2 | It counts | test_counts |\n"
    )
    await services.get(DocumentService).write_document(
        first, DocumentName.REQUIREMENTS, DocumentWrite(content=text, base_version=1), by="alex"
    )
    summary = await board.evidence_summary(first)
    assert summary["not_proven"] == ["A1: It shows"]
    with pytest.raises(NotFoundError, match="no such ticket"):
        await board.evidence_summary("CF-999")


@pytest.mark.usefixtures("board_ids")
async def test_repositories_are_the_tracked_and_the_filed_in_by_name(
    board: BoardService,
) -> None:
    assert await board.repositories() == ["sample", "second"]


async def test_a_board_with_nothing_tracked_or_filed_names_no_repository(
    board: BoardService,
) -> None:
    assert await board.repositories() == []


async def test_the_archive_lists_a_ticket_taken_off_by_hand(
    board: BoardService, board_ids: dict[str, str]
) -> None:
    answer = await board.archive({})
    assert [r["id"] for r in answer["rows"]] == [board_ids["Archived"]]
    assert (answer["sort"], answer["dir"], answer["archived_count"]) == ("archived", "desc", 1)
    assert answer["rows"][0]["release"] == ""


@pytest.mark.usefixtures("board_ids")
async def test_the_archive_is_paged_and_refuses_a_bad_page(board: BoardService) -> None:
    paged = await board.archive({"page": "1", "size": "10"})
    assert (paged["total"], paged["page"], paged["size"]) == (1, 1, 10)
    with pytest.raises(BadRequestError, match="page must be a whole number from 1"):
        await board.archive({"page": "0"})
    with pytest.raises(BadRequestError, match="size must be a whole number from 1 to 100"):
        await board.archive({"size": "101"})


@pytest.mark.usefixtures("board_ids")
async def test_the_archive_follows_the_query(board: BoardService) -> None:
    assert (await board.archive({"q": "zzz"}))["rows"] == []
    assert len((await board.archive({"q": "arch"}))["rows"]) == 1
    assert (await board.archive({"show": "released"}))["rows"] == []


async def test_a_read_writes_nothing(
    board: BoardService, connection: AsyncConnection, board_ids: dict[str, str]
) -> None:
    with recorded(connection) as seen:
        await board.board()
        await board.tickets({})
        await board.ticket_page("sample", board_ids["A bug in flight"])
        await board.archive({})
        await board.repositories()
    assert seen
    writes = [s for s in seen if not s.lstrip().upper().startswith(READS)]
    assert writes == []


async def count_statements(
    board: BoardService, connection: AsyncConnection
) -> tuple[int, int, int]:
    with recorded(connection) as seen:
        await board.board()
    first = len(seen)
    with recorded(connection) as seen:
        await board.tickets({})
    with recorded(connection) as page_seen:
        await board.archive({})
    return first, len(seen), len(page_seen)


async def test_the_statements_of_a_read_do_not_grow_with_the_tickets(
    board: BoardService,
    tickets: TicketService,
    connection: AsyncConnection,
    board_ids: dict[str, str],
) -> None:
    assert board_ids
    before = await count_statements(board, connection)
    for number in range(30):
        await tickets.create(NewTicket(repository="sample", title=f"More {number}"), by="alex")
    after = await count_statements(board, connection)
    assert after == before


async def test_a_run_and_its_end_are_one_line_that_carries_what_the_run_received(
    sources: BoardSources,
    uow: UnitOfWork,
    services: Services,
    board_ids: dict[str, str],
) -> None:
    bug = board_ids["A bug in flight"]
    activity = services.get(ActivityService)
    started = {"run": "r1", "stage": "build", "agent": "claude", "iteration": 2}
    await activity.append(bug, NewActivity(kind="run.started", data=started), by="run:r1")
    await activity.append(
        bug, NewActivity(kind="run.ended", data={"run": "r1", "exit_code": 0}), by="run:r1"
    )
    records = {"r1": RunRecord(memory={"version": 3}, context_at=1790000000.0)}
    page = await with_ports(sources, uow, runs=FakeRuns(records=records)).ticket_page("sample", bug)
    [run] = [line for line in page["activity"] if line["kind"] == "run"]
    assert (run["run"], run["agent"], run["iteration"], run["outcome"]) == (
        "r1",
        "claude",
        2,
        "finished",
    )
    assert (run["memory"], run["context_at"]) == ({"version": 3}, 1790000000.0)
    assert [line["kind"] for line in page["activity"]].count("run.ended") == 0


async def test_the_page_keeps_the_newest_hundred_lines_newest_first(
    board: BoardService, services: Services, board_ids: dict[str, str]
) -> None:
    bug = board_ids["A bug in flight"]
    activity = services.get(ActivityService)
    for number in range(103):
        await activity.append(bug, NewActivity(kind="note", data={"text": f"n{number}"}), by="alex")
    lines = (await board.ticket_page("sample", bug))["activity"]
    assert len(lines) == 100
    assert lines[0]["text"] == "n102"
    assert "n0" not in {line["text"] for line in lines}


async def test_a_non_finite_repository_budget_is_no_budget(
    board: BoardService, services: Services, tmp_path: Path, board_ids: dict[str, str]
) -> None:
    root = tmp_path / "sample"
    (root / ".code-factory").mkdir(parents=True)
    (root / ".code-factory" / "config.toml").write_text(
        "[agents]\nbudget_usd = nan\nmonthly_budget_usd = inf\n"
    )
    await services.get(RepositoryService).track(root)
    page = await board.ticket_page("sample", board_ids["Worked on main"])
    assert (page["default_budget"], page["month_budget"]) == (None, None)
    json.dumps(page, allow_nan=False)


async def test_a_run_started_beyond_the_newest_hundred_lines_still_folds_with_its_end(
    board: BoardService, services: Services, board_ids: dict[str, str]
) -> None:
    bug = board_ids["A bug in flight"]
    activity = services.get(ActivityService)
    await activity.append(bug, NewActivity(kind="run.started", data={"run": "r9"}), by="run:r9")
    for number in range(50):
        run = {"run": f"p{number}"}
        await activity.append(bug, NewActivity(kind="run.started", data=run), by="run:p")
        await activity.append(bug, NewActivity(kind="run.ended", data=run), by="run:p")
    await activity.append(bug, NewActivity(kind="run.ended", data={"run": "r9"}), by="run:r9")
    kinds = [line["kind"] for line in (await board.ticket_page("sample", bug))["activity"]]
    assert kinds.count("run") == 51
    assert "run.ended" not in kinds
