"""The runs the team module reads: ids, epoch seconds and the active ones with their liveness."""

from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.runs.repository import RunRepository
from code_factory.runs.service import RunService
from code_factory.runs.service.neighbours import TeamRunSource
from code_factory.tickets.models import Ticket
from runs_values import NOW, a_run, at


async def test_an_ended_run_is_read_with_the_ticket_key_and_epoch_seconds(
    runs: RunService, db_session: AsyncSession, ticket: Ticket
) -> None:
    await RunRepository(db_session).insert(
        a_run(
            ticket.number,
            agent="writer",
            exit_code=0,
            ended_at=at(90),
            tokens=1500,
            cost=0.25,
            limited_until=at(3600),
            uncommitted=True,
        )
    )
    [found] = await TeamRunSource(lambda: runs).runs_on_ticket(ticket.id)
    assert (found.id, found.ticket_id, found.repository, found.stage) == (
        "a1b2c3d4e5f6",
        ticket.id,
        "sample",
        "build",
    )
    assert found.agent == "writer"
    assert found.started_at == NOW.timestamp()
    assert found.ended_at == NOW.timestamp() + 90
    assert (found.exit_code, found.tokens, found.cost, found.uncommitted) == (0, 1500, 0.25, True)
    assert found.limited_until == NOW.timestamp() + 3600
    assert found.active is False


async def test_runs_since_a_moment_leave_out_older_ones(
    runs: RunService, db_session: AsyncSession, ticket: Ticket
) -> None:
    repo = RunRepository(db_session)
    await repo.insert(a_run(ticket.number, "aaaaaaaaaaaa", started_at=at(-10), exit_code=0))
    await repo.insert(a_run(ticket.number, "bbbbbbbbbbbb", started_at=at(0), attempt=1))
    source = TeamRunSource(lambda: runs)
    assert [r.id for r in await source.runs_since(NOW.timestamp())] == ["bbbbbbbbbbbb"]
    assert [r.id for r in await source.runs_by_ids(["aaaaaaaaaaaa", "ffffffffffff"])] == [
        "aaaaaaaaaaaa"
    ]


async def test_an_active_run_whose_process_is_gone_is_not_alive(
    runs: RunService, db_session: AsyncSession, ticket: Ticket
) -> None:
    await RunRepository(db_session).insert(a_run(ticket.number, pid=4242))
    [active] = await TeamRunSource(lambda: runs).active_runs()
    assert active.run.active is True
    assert active.alive is False
