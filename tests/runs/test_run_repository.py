import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.errors import ConflictError
from code_factory.runs.repository import RunEnd, RunRepository
from code_factory.tickets.models import Ticket
from runs_values import NOW, a_run, at


async def test_a_run_is_read_back_as_it_was_written(
    run_repo: RunRepository, ticket: Ticket
) -> None:
    await run_repo.insert(a_run(ticket.number, cost=1.25, commits=[], tokens=7, agent="writer"))
    found = await run_repo.get("a1b2c3d4e5f6")
    assert found is not None
    assert (found.cost, found.commits, found.tokens, found.agent) == (1.25, [], 7, "writer")
    assert found.pid is None
    assert found.exit_code is None


async def test_commits_never_recorded_stay_distinct_from_none_made(
    run_repo: RunRepository, ticket: Ticket
) -> None:
    await run_repo.insert(a_run(ticket.number))
    found = await run_repo.get("a1b2c3d4e5f6")
    assert found is not None
    assert found.commits is None


async def test_an_unknown_run_is_none(run_repo: RunRepository) -> None:
    assert await run_repo.get("000000000000") is None


async def test_a_second_active_run_of_a_ticket_and_attempt_is_refused(
    run_repo: RunRepository, ticket: Ticket
) -> None:
    await run_repo.insert(a_run(ticket.number, "aaaaaaaaaaaa"))
    with pytest.raises(ConflictError, match="an agent is already running on this ticket"):
        await run_repo.insert(a_run(ticket.number, "bbbbbbbbbbbb"))


async def test_another_attempt_of_the_same_ticket_may_run_beside_it(
    run_repo: RunRepository, ticket: Ticket
) -> None:
    await run_repo.insert(a_run(ticket.number, "aaaaaaaaaaaa", attempt=0))
    await run_repo.insert(a_run(ticket.number, "bbbbbbbbbbbb", attempt=1))
    assert {r.id for r in await run_repo.active()} == {"aaaaaaaaaaaa", "bbbbbbbbbbbb"}


async def test_a_ticket_may_run_again_once_its_run_ended(
    run_repo: RunRepository, ticket: Ticket
) -> None:
    await run_repo.insert(a_run(ticket.number, "aaaaaaaaaaaa"))
    await run_repo.end("aaaaaaaaaaaa", RunEnd(exit_code=0, ended_at=at(5)))
    await run_repo.insert(a_run(ticket.number, "bbbbbbbbbbbb"))
    assert [r.id for r in await run_repo.active()] == ["bbbbbbbbbbbb"]


async def test_a_second_active_coordinator_of_a_repository_is_refused(
    run_repo: RunRepository,
) -> None:
    await run_repo.insert(a_run(None, "aaaaaaaaaaaa", stage="coordinate"))
    with pytest.raises(ConflictError, match="a coordinator is already running for sample"):
        await run_repo.insert(a_run(None, "bbbbbbbbbbbb", stage="coordinate"))
    await run_repo.insert(a_run(None, "cccccccccccc", stage="coordinate", repository="other"))


async def test_the_database_refuses_an_unknown_stage_by_name(
    run_repo: RunRepository, db_session: AsyncSession, ticket: Ticket
) -> None:
    await run_repo.insert(a_run(ticket.number))
    with pytest.raises(IntegrityError, match="ck_runs_known_stage"):
        async with db_session.begin_nested():
            await db_session.execute(text("update runs set stage = 'deploy'"))


async def test_the_database_refuses_an_unknown_permission_mode_by_name(
    run_repo: RunRepository, db_session: AsyncSession, ticket: Ticket
) -> None:
    await run_repo.insert(a_run(ticket.number))
    with pytest.raises(IntegrityError, match="ck_runs_known_mode"):
        async with db_session.begin_nested():
            await db_session.execute(text("update runs set permissions = 'anything'"))


async def test_an_end_is_won_by_the_first_and_refused_to_the_second(
    run_repo: RunRepository, ticket: Ticket
) -> None:
    await run_repo.insert(a_run(ticket.number))
    first = await run_repo.end(
        "a1b2c3d4e5f6", RunEnd(exit_code=0, ended_at=at(5), cost=0.5, tokens=9, commits=["abc"])
    )
    second = await run_repo.end("a1b2c3d4e5f6", RunEnd(exit_code=1, ended_at=at(6)))
    assert first is not None
    assert (first.exit_code, first.ended_at, first.cost, first.commits) == (0, at(5), 0.5, ["abc"])
    assert second is None
    kept = await run_repo.get("a1b2c3d4e5f6")
    assert kept is not None
    assert kept.exit_code == 0


async def test_a_pid_is_recorded_only_for_a_run_with_no_exit(
    run_repo: RunRepository, ticket: Ticket
) -> None:
    await run_repo.insert(a_run(ticket.number))
    assert await run_repo.set_pid("a1b2c3d4e5f6", 4242, at(1))
    await run_repo.end("a1b2c3d4e5f6", RunEnd(exit_code=0, ended_at=at(2)))
    assert not await run_repo.set_pid("a1b2c3d4e5f6", 9999, at(3))
    kept = await run_repo.get("a1b2c3d4e5f6")
    assert kept is not None
    assert (kept.pid, kept.pid_started_at) == (4242, at(1))


async def test_unsettled_runs_are_the_ended_ones_with_no_settled_time(
    run_repo: RunRepository, ticket: Ticket
) -> None:
    await run_repo.insert(a_run(ticket.number))
    assert await run_repo.unsettled() == []
    await run_repo.end("a1b2c3d4e5f6", RunEnd(exit_code=0, ended_at=at(2)))
    assert [r.id for r in await run_repo.unsettled()] == ["a1b2c3d4e5f6"]
    await run_repo.settle("a1b2c3d4e5f6", at(3))
    assert await run_repo.unsettled() == []


async def test_a_run_with_no_pid_older_than_a_minute_is_stale(
    run_repo: RunRepository, ticket: Ticket
) -> None:
    await run_repo.insert(a_run(ticket.number, started_at=at(-61)))
    assert [r.id for r in await run_repo.unspawned_before(at(-60))] == ["a1b2c3d4e5f6"]
    assert await run_repo.unspawned_before(at(-62)) == []
    assert await run_repo.unspawned_before(at(-61)) == []
    await run_repo.set_pid("a1b2c3d4e5f6", 5000, at(-59))
    assert await run_repo.unspawned_before(at(-60)) == []


async def test_cost_between_is_half_open_and_counts_no_cost_as_nothing(
    run_repo: RunRepository, ticket: Ticket
) -> None:
    for run_id, when, cost, attempt in [
        ("aaaaaaaaaaaa", at(0), 1.0, 0),
        ("bbbbbbbbbbbb", at(10), 2.0, 1),
        ("cccccccccccc", at(5), None, 2),
        ("dddddddddddd", at(-1), 4.0, 3),
    ]:
        await run_repo.insert(
            a_run(ticket.number, run_id, started_at=when, cost=cost, attempt=attempt)
        )
    assert await run_repo.cost_between("sample", at(0), at(10)) == pytest.approx(1.0)
    assert await run_repo.cost_between("sample", at(0), at(11)) == pytest.approx(3.0)
    assert await run_repo.cost_between("other", at(-100), at(100)) == 0.0


async def test_a_ticket_costs_the_sum_of_its_runs(run_repo: RunRepository, ticket: Ticket) -> None:
    await run_repo.insert(a_run(ticket.number, "aaaaaaaaaaaa", cost=1.5, attempt=0))
    await run_repo.insert(a_run(ticket.number, "bbbbbbbbbbbb", cost=2.25, attempt=1))
    assert await run_repo.ticket_cost(ticket.number) == pytest.approx(3.75)


async def test_runs_of_a_ticket_are_newest_first_and_capped(
    run_repo: RunRepository, ticket: Ticket
) -> None:
    for n, run_id in enumerate(["aaaaaaaaaaaa", "bbbbbbbbbbbb", "cccccccccccc"]):
        await run_repo.insert(a_run(ticket.number, run_id, started_at=at(n), exit_code=0))
    found = await run_repo.for_ticket(ticket.number, limit=2)
    assert [r.id for r in found] == ["cccccccccccc", "bbbbbbbbbbbb"]


async def test_the_latest_run_of_each_named_agent(run_repo: RunRepository, ticket: Ticket) -> None:
    await run_repo.insert(
        a_run(ticket.number, "aaaaaaaaaaaa", agent="x", started_at=at(1), attempt=0)
    )
    await run_repo.insert(
        a_run(ticket.number, "bbbbbbbbbbbb", agent="x", started_at=at(2), attempt=1)
    )
    await run_repo.insert(
        a_run(ticket.number, "cccccccccccc", agent="y", started_at=at(0), attempt=2)
    )
    found = await run_repo.latest_by_agent(["x", "y", "z"])
    assert sorted(r.id for r in found) == ["bbbbbbbbbbbb", "cccccccccccc"]


async def test_runs_since_a_moment_include_that_moment(
    run_repo: RunRepository, ticket: Ticket
) -> None:
    await run_repo.insert(a_run(ticket.number, "aaaaaaaaaaaa", started_at=at(-1), attempt=0))
    await run_repo.insert(a_run(ticket.number, "bbbbbbbbbbbb", started_at=NOW, attempt=1))
    assert [r.id for r in await run_repo.since(NOW)] == ["bbbbbbbbbbbb"]
