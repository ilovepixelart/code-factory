"""The keeper's upkeep: lost runs, stopping, pruning, flaky bugs and the pending status."""

from pathlib import Path
from typing import Any

import pytest

from checks_support import REPO, Clock, FakeForge, write_config
from code_factory.checks.models import PullHead, RunState
from code_factory.checks.repository import CheckStore
from code_factory.checks.service import CheckService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.tickets.models import NewTicket, Ticket
from code_factory.tickets.service import ActivityService, TicketService
from ticket_values import OWNER

PLAIN = "[checks]\ncommand = 'true'\n[agents]\nsandbox = false\n"


async def insert(uow: UnitOfWork, subject: str, clock: Clock, owner: str = "me") -> int:
    async with uow() as session:
        row = await CheckStore(session).runs.insert(
            {
                "repository": REPO,
                "subject": subject,
                "scope": "reached",
                "commit": "a" * 40,
                "tree_id": "b" * 40,
                "state": "queued",
                "contained": "none",
                "owner": owner,
                "requested_by": "alex",
                "queued_at": clock.now,
                "beat_at": clock.now,
            }
        )
    assert row is not None
    return row.id


async def test_a_run_unbeaten_for_a_minute_is_lost_and_one_beaten_59_seconds_ago_is_not(
    checks: CheckService, uow: UnitOfWork, clock: Clock
) -> None:
    quiet = await insert(uow, "CF-1", clock)
    clock.after(seconds=59)
    assert await checks.reconcile() == 0
    assert (await checks.get(quiet)).state is RunState.QUEUED
    clock.after(seconds=2)
    assert await checks.reconcile() == 1
    assert (await checks.get(quiet)).state is RunState.LOST


async def test_a_run_of_another_process_cannot_be_stopped_from_this_one(
    checks: CheckService, uow: UnitOfWork, clock: Clock
) -> None:
    foreign = await insert(uow, "CF-1", clock, owner="elsewhere:1:x")
    with pytest.raises(ConflictError, match="the check runs in another process"):
        await checks.stop(foreign, "alex")
    assert (await checks.get(foreign)).state is RunState.QUEUED


async def test_an_ended_run_cannot_be_stopped_again(
    checks: CheckService, started: Ticket, root: Path
) -> None:
    write_config(root, PLAIN)
    row = await checks.run_now(await checks.start(started.id))
    with pytest.raises(ConflictError, match="the check ended already"):
        await checks.stop(row.id, "alex")


async def test_a_stopped_run_this_process_holds_without_a_task_is_lost(
    checks: CheckService, started: Ticket, root: Path
) -> None:
    write_config(root, PLAIN)
    check_id = await checks.start(started.id)
    await checks.stop(check_id, "alex")
    assert (await checks.get(check_id)).state is RunState.LOST


async def test_prune_lists_what_is_old_and_removes_it_only_when_applied(
    checks: CheckService, started: Ticket, root: Path, clock: Clock
) -> None:
    write_config(root, PLAIN)
    row = await checks.run_now(await checks.start(started.id))
    log = Path(row.log_path)
    clock.after(days=40)
    assert (await checks.prune(60, apply=True)).runs == 0
    assert log.exists()
    listed = await checks.prune(30, apply=False)
    assert (listed.runs, listed.logs) == (1, [log.name])
    assert log.exists()
    done = await checks.prune(30, apply=True)
    assert (done.runs, done.logs) == (1, [log.name])
    assert not log.exists()
    assert (await checks.prune(30, apply=False)).runs == 0


async def test_pending_is_posted_only_while_the_commit_is_the_open_head(
    checks: CheckService, forge: FakeForge, started: Ticket, root: Path
) -> None:
    write_config(root, PLAIN)
    forge.heads.append(PullHead(repository=REPO, ticket_id=started.id, head="f" * 40))
    await checks.run_now(await checks.start(started.id))
    assert "pending" not in forge.states()


async def records(activity: ActivityService, ticket: Ticket, kind: str) -> list[dict[str, Any]]:
    page = await activity.list_activity(ticket.id, kinds=[kind], limit=100)
    return [item.data for item in page.items]


async def test_a_bug_is_attached_to_the_flaky_tree_of_the_newest_check(
    checks: CheckService,
    activity: ActivityService,
    tickets: TicketService,
    started: Ticket,
    root: Path,
) -> None:
    write_config(root, PLAIN)
    await checks.run_now(await checks.start(started.id))
    (newest,) = await records(activity, started, "checks")
    bug = await tickets.create(NewTicket(repository=REPO, title="Flaky", type="bug"), by=OWNER)
    assert await checks.attach_flaky(started.id, bug.id, "alex") == newest["tree"]
    (flaky,) = await records(activity, started, "flaky")
    assert (flaky["bug"], flaky["tree"]) == (bug.id, newest["tree"])


async def test_a_ticket_that_is_not_a_bug_or_a_ticket_without_a_check_is_refused(
    checks: CheckService, tickets: TicketService, started: Ticket
) -> None:
    other = await tickets.create(NewTicket(repository=REPO, title="Plain"), by=OWNER)
    bug = await tickets.create(NewTicket(repository=REPO, title="A bug", type="bug"), by=OWNER)
    with pytest.raises(BadRequestError, match="is not a bug ticket"):
        await checks.attach_flaky(started.id, other.id, "alex")
    with pytest.raises(NotFoundError, match="has no recorded check"):
        await checks.attach_flaky(started.id, bug.id, "alex")
