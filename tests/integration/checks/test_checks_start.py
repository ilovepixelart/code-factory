"""Starting a check: the row it queues and the refusals, each with its sentence."""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from checks_support import REPO, write_config
from code_factory.checks.models import RunState, Scope
from code_factory.checks.service import CheckService
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.tickets.models import NewTicket, Ticket
from code_factory.tickets.service import TicketService
from git_support import git
from ticket_values import OWNER

PLAIN = '[checks]\ncommand = "true"\n[agents]\nsandbox = false\n'


async def test_start_queues_a_row_for_the_tip_of_the_ticket_branch(
    checks: CheckService, started: Ticket, root: Path
) -> None:
    write_config(root, PLAIN)
    tip = git(root, "rev-parse", "ticket/cf-1")
    check_id = await checks.start(started.id)
    row = await checks.get(check_id)
    assert (row.subject, row.repository, row.commit, row.state) == (
        started.id,
        REPO,
        tip,
        RunState.QUEUED,
    )
    assert row.scope is Scope.REACHED
    assert row.requested_by == "board"
    assert row.tree_id == git(root, "rev-parse", f"{tip}^{{tree}}")


async def test_start_for_a_given_head_queues_that_commit(
    checks: CheckService, started: Ticket, root: Path
) -> None:
    write_config(root, PLAIN)
    first = git(root, "rev-parse", "main")
    check_id = await checks.start(started.id, head=first, by="owner")
    row = await checks.get(check_id)
    assert (row.commit, row.requested_by) == (first, "owner")


async def test_a_second_start_while_one_is_queued_is_the_conflict_and_leaves_one_row(
    checks: CheckService, started: Ticket, root: Path
) -> None:
    write_config(root, PLAIN)
    await checks.start(started.id)
    with pytest.raises(ConflictError, match=r"^checks are already running for this ticket$"):
        await checks.start(started.id)
    assert len(await checks.recent_runs(subject=started.id)) == 1


async def test_a_ticket_that_does_not_exist_is_not_found(checks: CheckService) -> None:
    with pytest.raises(NotFoundError, match=r"^no such ticket$"):
        await checks.start("CF-999")


async def test_a_repository_without_a_checks_command_refuses(
    checks: CheckService, started: Ticket
) -> None:
    with pytest.raises(
        BadRequestError, match=r"^no checks command in \.code-factory/config\.toml$"
    ):
        await checks.start(started.id)


async def test_the_fast_scope_wants_its_own_command(
    checks: CheckService, started: Ticket, root: Path
) -> None:
    write_config(root, PLAIN)
    with pytest.raises(
        BadRequestError, match=r"^no \[checks\] fast command in \.code-factory/config\.toml$"
    ):
        await checks.start(started.id, Scope.FAST)
    write_config(root, PLAIN.replace('command = "true"', 'command = "true"\nfast = "true"'))
    assert await checks.start(started.id, Scope.FAST) > 0


async def test_a_ticket_without_a_branch_refuses(
    checks: CheckService, tickets: TicketService, root: Path
) -> None:
    write_config(root, PLAIN)
    made = await tickets.create(NewTicket(repository=REPO, title="No branch"), by=OWNER)
    with pytest.raises(BadRequestError, match=r"^the ticket has no branch$"):
        await checks.start(made.id)


async def test_a_head_is_queued_once_while_its_checks_wait(
    checks: CheckService, started: Ticket, root: Path
) -> None:
    write_config(root, PLAIN)
    tip = git(root, "rev-parse", "ticket/cf-1")

    first = await checks.queue_head(started.id, tip)
    again = await checks.queue_head(started.id, tip)

    assert first is not None
    assert (await checks.get(first)).commit == tip
    assert again is None
    assert len(await checks.recent_runs(subject=started.id)) == 1


async def test_a_head_whose_checks_gave_a_verdict_is_not_queued_again(
    checks: CheckService, started: Ticket, root: Path
) -> None:
    write_config(root, PLAIN)
    tip = git(root, "rev-parse", "ticket/cf-1")
    await checks.run_now(await checks.start(started.id))

    assert await checks.queue_head(started.id, tip) is None
    assert len(await checks.recent_runs(subject=started.id)) == 1


async def test_no_head_is_queued_where_no_checks_command_is_set(
    checks: CheckService, started: Ticket, root: Path
) -> None:
    tip = git(root, "rev-parse", "ticket/cf-1")

    assert await checks.queue_head(started.id, tip) is None
    assert await checks.recent_runs(subject=started.id) == []


async def test_start_holds_under_a_generic_plan_of_the_insert(
    checks: CheckService, started: Ticket, root: Path, connection: AsyncConnection
) -> None:
    write_config(root, PLAIN)
    await connection.exec_driver_sql("SET LOCAL plan_cache_mode = force_generic_plan")
    assert await checks.start(started.id) > 0
    with pytest.raises(ConflictError, match=r"^checks are already running for this ticket$"):
        await checks.start(started.id)
