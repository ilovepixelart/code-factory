"""The inbox over the real services of the app: a question and a failing pull request show."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI

from checks_support import write_config
from code_factory.delivery.models import PullReading
from code_factory.delivery.repository import DeliveryRepository
from code_factory.delivery.service import DeliveryService
from code_factory.inbox.service import InboxService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.runs.repository import RunRepository
from code_factory.runs.service import HALTED, RunService
from code_factory.talk.models import Reply
from code_factory.talk.service import TalkService
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService
from git_support import git, make_repo
from runs_values import a_run


async def test_an_open_question_and_a_failing_pull_request_wait_on_the_owner(
    app: FastAPI, uow: UnitOfWork
) -> None:
    services = app.state.services
    tickets = services.get(TicketService)
    asked = await tickets.create(NewTicket(repository="sample", title="Pick a palette"), by="o")
    failing = await tickets.create(NewTicket(repository="sample", title="Retry uploads"), by="o")
    await services.get(TalkService).ask(asked.id, "Which colour?", [], by="agent")
    url = "https://github.com/o/r/pull/13"
    async with uow() as session:
        await DeliveryRepository(session).record_pull(
            failing.id, "sample", url, PullReading(state="open", ci="failed"), datetime.now(UTC)
        )

    page = await services.get(InboxService).page()

    assert [i["question"]["text"] for i in page["questions"]] == ["Which colour?"]
    assert [(i["kind"], i["reason"], i["ticket"]["id"]) for i in page["failing"]] == [
        ("failing", url, failing.id)
    ]
    assert await services.get(InboxService).count() == {
        "count": 2,
        "latest": page["latest"],
    }
    assert page["count"] == 2
    assert page["latest"] in {
        f"{asked.id} asks: Which colour?",
        f"{failing.id}: CI failed on its pull request",
    }
    assert (await services.get(InboxService).waiting_ticket_ids()) == {asked.id, failing.id}


async def _green_pull(
    app: FastAPI, uow: UnitOfWork, root: Path, size: dict[str, int] | None = None
) -> str:
    """A ticket of the tracked `sample`: its pull request open, green, at its shipped head."""
    services = cast("Services", app.state.services)
    await services.get(RepositoryService).track(root)
    ticket = await services.get(TicketService).create(
        NewTicket(repository="sample", title="Add subtract"), by="o"
    )
    head = git(root, "rev-parse", "HEAD")
    async with uow() as session:
        store = DeliveryRepository(session)
        await store.record_pull(
            ticket.id,
            "sample",
            "https://github.com/o/r/pull/1",
            PullReading.model_validate(
                {"state": "open", "ci": "passed", "head": head, **(size or {})}
            ),
            datetime.now(UTC),
        )
        await store.set_shipped(ticket.id, head)
    return ticket.id


async def test_an_open_pull_is_idle_after_two_days_without_a_host_update(
    app: FastAPI, uow: UnitOfWork
) -> None:
    services = app.state.services
    ticket = await services.get(TicketService).create(
        NewTicket(repository="sample", title="Review the update"), by="o"
    )
    now = datetime.now(UTC)
    last_update = now - timedelta(days=3)
    url = "https://github.com/o/r/pull/13"
    async with uow() as session:
        await DeliveryRepository(session).record_pull(
            ticket.id, "sample", url, PullReading(state="open", updated_on_host=last_update), now
        )

    page = await services.get(InboxService).page()

    assert [item["since"] for item in page["idle"]] == [last_update.timestamp()]
    assert page["count"] == 1


async def test_question_response_time_counts_the_first_answer_only(
    app: FastAPI, uow: UnitOfWork
) -> None:
    services = app.state.services
    ticket = await services.get(TicketService).create(
        NewTicket(repository="sample", title="Ask once"), by="o"
    )
    asked_at = datetime.now(UTC)
    q = await TalkService(uow, clock=lambda: asked_at).ask(ticket.id, "Which colour?", [], by="a")
    for seconds, replace in [(60, False), (120, True)]:
        answered_at = asked_at + timedelta(seconds=seconds)
        talk = TalkService(uow, clock=lambda at=answered_at: at)
        await talk.answer(
            q.question_id, Reply(text="Green"), replace=replace, by="o", channel="http"
        )

    wait = await services.get(TalkService).question_wait(asked_at, asked_at + timedelta(minutes=5))

    assert wait.answered == 1
    assert wait.median_seconds == 60


async def test_a_green_pull_request_is_ready_to_merge_when_the_board_runs_no_checks(
    app: FastAPI, uow: UnitOfWork, tmp_path: Path
) -> None:
    ticket = await _green_pull(app, uow, make_repo(tmp_path))

    page = await app.state.services.get(InboxService).page()

    assert [i["ticket"]["id"] for i in page["mergeable"]] == [ticket]


async def test_a_merge_item_carries_the_pull_requests_size_when_github_counted_it(
    app: FastAPI, uow: UnitOfWork, tmp_path: Path
) -> None:
    size = {"additions": 1240, "deletions": 380, "changed_files": 27}
    await _green_pull(app, uow, make_repo(tmp_path), size)

    page = await app.state.services.get(InboxService).page()

    assert [i["size"] for i in page["mergeable"]] == [size]


async def test_a_merge_item_without_a_count_has_no_size(
    app: FastAPI, uow: UnitOfWork, tmp_path: Path
) -> None:
    await _green_pull(app, uow, make_repo(tmp_path))

    page = await app.state.services.get(InboxService).page()

    assert [i["size"] for i in page["mergeable"]] == [None]


async def test_a_pull_request_waiting_for_the_boards_checks_is_not_ready_to_merge(
    app: FastAPI, uow: UnitOfWork, tmp_path: Path
) -> None:
    root = make_repo(tmp_path)
    write_config(root, "[checks]\ncommand = 'true'\n")
    await _green_pull(app, uow, root)

    page = await app.state.services.get(InboxService).page()

    assert page["mergeable"] == []


async def test_a_repository_that_merges_on_its_own_asks_the_owner_only_when_a_hold_names_it(
    app: FastAPI, uow: UnitOfWork, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    write_config(root, "[agents]\nmerge_approval = false\n")
    ticket = await _green_pull(app, uow, root)
    head = git(root, "rev-parse", "HEAD")
    delivery = app.state.services.get(DeliveryService)
    holds = {(ticket, head): "the change touches a sensitive path"}
    monkeypatch.setattr(delivery, "owner_hold", lambda t, h: holds.get((t, h), ""))

    page = await app.state.services.get(InboxService).page()

    assert [(i["ticket"]["id"], i["note"]) for i in page["mergeable"]] == [
        (ticket, "the change touches a sensitive path")
    ]


async def test_a_repository_that_merges_on_its_own_leaves_an_unheld_pull_to_the_board(
    app: FastAPI, uow: UnitOfWork, tmp_path: Path
) -> None:
    root = make_repo(tmp_path)
    write_config(root, "[agents]\nmerge_approval = false\n")
    await _green_pull(app, uow, root)

    page = await app.state.services.get(InboxService).page()

    assert page["mergeable"] == []


async def _refused_by_the_halt(app: FastAPI, uow: UnitOfWork, reason: str) -> str:
    """A ticket whose newest run ended before its process started, with `reason`."""
    services = cast("Services", app.state.services)
    ticket = await services.get(TicketService).create(
        NewTicket(repository="sample", title="Wait for the hold"), by="o"
    )
    now = datetime.now(UTC)
    async with uow() as session:
        await RunRepository(session).insert(
            a_run(
                ticket.number,
                f"{ticket.number:012d}",
                exit_code=-1,
                ended_at=now,
                started_at=now,
                halted=reason,
            )
        )
    return ticket.id


async def test_a_run_refused_by_the_hold_is_stopped_while_agents_are_held(
    app: FastAPI, uow: UnitOfWork
) -> None:
    ticket = await _refused_by_the_halt(app, uow, HALTED)
    await app.state.services.get(RunService).stop_all("owner:owner")

    page = await app.state.services.get(InboxService).page()

    assert [(i["reason"], i["ticket"]["id"]) for i in page["stopped"]] == [(HALTED, ticket)]


async def test_a_run_refused_by_the_hold_leaves_the_stopped_agents_once_they_resume(
    app: FastAPI, uow: UnitOfWork
) -> None:
    await _refused_by_the_halt(app, uow, HALTED)
    other = await _refused_by_the_halt(app, uow, "agent failed (exit 1)")
    runs = app.state.services.get(RunService)
    await runs.stop_all("owner:owner")
    await runs.resume()

    page = await app.state.services.get(InboxService).page()

    assert [(i["reason"], i["ticket"]["id"]) for i in page["stopped"]] == [
        ("agent failed (exit 1)", other)
    ]
