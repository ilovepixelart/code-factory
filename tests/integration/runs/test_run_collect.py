"""Collecting ended runs: the exit file, the log's facts, the side effects once and in order."""

import asyncio
import signal
from datetime import timedelta

import pytest

from code_factory.platform.errors import NotFoundError
from code_factory.runs.models import Run
from code_factory.runs.ports import Given, Limit, LogUsage, TicketFacts
from code_factory.runs.repository import RunEnd, RunRepository
from code_factory.runs.service import RunService
from runs_fakes import Fakes
from runs_values import NOW, FakeClock, a_run


async def started(runs: RunService, facts: TicketFacts) -> Run:
    return (await runs.start(facts.id)).runs[0]


async def wait_for_exit(runs: RunService, run: Run) -> None:
    for _ in range(200):
        if runs.exit_path(run.id).exists():
            return
        await asyncio.sleep(0.05)
    pytest.fail("the run never wrote its exit file")


async def test_a_collection_ends_a_run_with_the_code_its_wrapper_recorded(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository, clock: FakeClock
) -> None:
    fakes.agents.script = "exit 3"
    run = await started(runs, facts)
    await wait_for_exit(runs, run)
    clock.advance(10)
    (ended,) = await runs.collect()
    assert ended.run.id == run.id
    assert (ended.run.exit_code, ended.run.ended_at) == (3, NOW + timedelta(seconds=10))
    assert ended.stopped is False
    kept = await run_repo.get(run.id)
    assert kept is not None
    assert kept.settled_at == NOW + timedelta(seconds=10)
    tail = fakes.calls.log[fakes.calls.log.index("event:run.ended") :]
    assert tail[:3] == ["event:run.ended", "fetch_back", "end_claim"]
    assert [e[1] for e in fakes.tickets.events] == ["run.started", "run.ended"]
    assert fakes.calls.log.count("revoke") == 1


async def test_a_run_still_running_is_left_alone(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.agents.script = "sleep 30"
    run = await started(runs, facts)
    assert await runs.collect() == []
    kept = await run_repo.get(run.id)
    assert kept is not None
    assert kept.exit_code is None


@pytest.mark.parametrize(
    "case", [("kill -9 $$", -signal.SIGKILL), ("exit 1", 1), ("exit 0", 0)], ids=str
)
async def test_a_process_that_ended_without_an_exit_file_is_recorded_with_its_return_code(
    runs: RunService, fakes: Fakes, facts: TicketFacts, case: tuple[str, int]
) -> None:
    command, code = case
    fakes.agents.argv = ("/bin/sh", "-c", command)
    (run,) = (await runs.start(facts.id, stage="spec")).runs
    for _ in range(100):
        if await runs.collect():
            break
        await asyncio.sleep(0.05)
    assert (await runs.get(run.id)).exit_code == code


async def test_an_adopted_process_that_is_gone_without_an_exit_file_is_unknown(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.agents.argv = ("/bin/sh", "-c", "kill -9 $$")
    run = await started(runs, facts)
    for _ in range(100):
        if runs._registry.returncode(run.pid or 0) is not None:  # the held process
            break
        await asyncio.sleep(0.05)
    runs._registry.detach_all()  # a restarted board holds nothing
    assert [e.run.id for e in await runs.collect()] == [run.id]
    kept = await run_repo.get(run.id)
    assert kept is not None
    assert kept.exit_code == -1


async def test_the_logs_reported_cost_is_recorded_as_reported(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "exit 0"
    fakes.agents.usage = LogUsage(cost=0.12, input_tokens=100, output_tokens=50, model="b")
    run = await started(runs, facts)
    await wait_for_exit(runs, run)
    (ended,) = await runs.collect()
    assert (ended.run.cost, ended.run.cost_estimated, ended.run.tokens, ended.run.model) == (
        0.12,
        False,
        150,
        "b",
    )


async def test_tokens_priced_by_the_agent_are_an_estimate_when_the_log_states_no_cost(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "exit 0"
    fakes.agents.given_value = Given(
        agent="writer",
        runtime="claude",
        model="m1",
        connection="c",
        fingerprint="f",
        input_price=3.0,
        output_price=15.0,
    )
    fakes.agents.usage = LogUsage(input_tokens=1_200_000, output_tokens=300_000)
    run = await started(runs, facts)
    await wait_for_exit(runs, run)
    (ended,) = await runs.collect()
    assert ended.run.cost == pytest.approx(8.10)
    assert ended.run.cost_estimated is True


async def test_tokens_with_no_price_and_no_stated_cost_leave_the_cost_unknown(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "exit 0"
    fakes.agents.usage = LogUsage(input_tokens=10, output_tokens=5)
    run = await started(runs, facts)
    await wait_for_exit(runs, run)
    (ended,) = await runs.collect()
    assert (ended.run.cost, ended.run.tokens) == (None, 15)


async def test_the_commits_a_run_made_are_recorded_and_it_is_not_uncommitted(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "exit 0"
    fakes.trees.heads = ["head0", "head1"]
    fakes.trees.new_commits = ["c1", "c2"]
    fakes.trees.dirty = True
    run = await started(runs, facts)
    await wait_for_exit(runs, run)
    (ended,) = await runs.collect()
    assert (ended.run.commits, ended.run.uncommitted) == (["c1", "c2"], False)


async def test_a_run_that_changed_files_and_committed_nothing_is_uncommitted(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "exit 0"
    fakes.trees.dirty = True
    run = await started(runs, facts)
    await wait_for_exit(runs, run)
    (ended,) = await runs.collect()
    assert (ended.run.commits, ended.run.uncommitted) == ([], True)


@pytest.mark.parametrize("case", [(None, 3600), (NOW.timestamp() + 10 + 60, 300)])
async def test_a_run_that_ended_on_a_usage_limit_waits_for_the_reset_or_the_floor(
    runs: RunService,
    fakes: Fakes,
    facts: TicketFacts,
    clock: FakeClock,
    case: tuple[float | None, int],
) -> None:
    reset, seconds = case
    fakes.agents.script = "exit 1"
    fakes.agents.limit = Limit(reset=reset)
    run = await started(runs, facts)
    await wait_for_exit(runs, run)
    clock.advance(10)
    (ended,) = await runs.collect()
    assert ended.run.limited_until == clock.now + timedelta(seconds=seconds)
    assert ended.limit_until == ended.run.limited_until
    assert "run.limited" in [e[1] for e in fakes.tickets.events]


async def test_two_passes_at_once_run_each_side_effect_once(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "exit 0"
    run = await started(runs, facts)
    await wait_for_exit(runs, run)
    first, second = await asyncio.gather(runs.collect(), runs.collect())
    assert len(first) + len(second) == 1
    assert [e[1] for e in fakes.tickets.events].count("run.ended") == 1
    assert fakes.calls.log.count("revoke") == 1


async def test_a_crash_between_the_end_and_its_side_effects_repeats_them_at_the_next_pass(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.agents.script = "exit 0"
    run = await started(runs, facts)
    await wait_for_exit(runs, run)
    await run_repo.end(run.id, RunEnd(exit_code=0, ended_at=NOW))  # ended, never settled
    assert [r.id for r in await run_repo.unsettled()] == [run.id]
    await runs.collect()
    assert await run_repo.unsettled() == []
    assert [e[1] for e in fakes.tickets.events].count("run.ended") == 1
    await runs.collect()
    assert fakes.calls.log.count("revoke") == 1


async def test_a_refused_fetch_back_is_told_on_the_ticket(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "exit 0"
    fakes.trees.refusal = "the clone holds a file past the limit"
    run = await started(runs, facts)
    await wait_for_exit(runs, run)
    await runs.collect()
    refused = [e for e in fakes.tickets.events if e[1] == "branch_refused"]
    assert len(refused) == 1
    assert refused[0][3]["reason"] == "the clone holds a file past the limit"


async def test_a_run_whose_process_was_never_recorded_is_ended_unknown_after_a_minute(
    runs: RunService, facts: TicketFacts, run_repo: RunRepository
) -> None:
    await run_repo.insert(
        a_run(facts.number, "aaaaaaaaaaaa", started_at=NOW - timedelta(seconds=61))
    )
    await run_repo.insert(
        a_run(None, "bbbbbbbbbbbb", stage="coordinate", started_at=NOW - timedelta(seconds=59))
    )
    ended = await runs.collect()
    assert [e.run.id for e in ended] == ["aaaaaaaaaaaa"]
    assert ended[0].run.exit_code == -1
    assert "never recorded a process" in ended[0].run.halted
    kept = await run_repo.get("bbbbbbbbbbbb")
    assert kept is not None
    assert kept.exit_code is None


async def test_a_fetch_back_that_fails_is_told_on_the_ticket_and_the_run_still_settles(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.agents.script = "exit 0"
    fakes.trees.fetch_error = NotFoundError("no tree cf-1-0 is recorded for sample")
    run = await started(runs, facts)
    await wait_for_exit(runs, run)
    (ended,) = await runs.collect()
    assert ended.run.settled_at is not None
    refused = [e for e in fakes.tickets.events if e[1] == "branch_refused"]
    assert [e[3]["reason"] for e in refused] == ["no tree cf-1-0 is recorded for sample"]
    assert fakes.calls.log.count("end_claim") == 1
    assert await run_repo.unsettled() == []
