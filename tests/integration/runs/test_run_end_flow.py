"""What the end of a run sets off: a build's commits go to their checks, a review to its verdict."""

import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import ConflictError, DatabaseBusyError
from code_factory.runs.adapters.processes import ProcessRegistry
from code_factory.runs.models import Run, StartOptions
from code_factory.runs.ports import TicketFacts
from code_factory.runs.rules.records import state_of
from code_factory.runs.service import RunService
from code_factory.tickets.rules.feed import describe
from runs_fakes import Fakes
from runs_values import FakeClock


async def _ended(runs: RunService, facts: TicketFacts, stage: str = "build") -> Run:
    (run,) = (await runs.start(facts.id, stage=stage)).runs
    for _ in range(200):
        if runs.exit_path(run.id).exists():
            break
        await asyncio.sleep(0.05)
    await runs.collect()
    return await runs.get(run.id)


@pytest.fixture
def committing(fakes: Fakes) -> Fakes:
    fakes.agents.script = "exit 0"
    fakes.trees.heads = ["head0", "head1"]
    fakes.trees.new_commits = ["c1", "c2"]
    return fakes


@pytest.fixture
def restart_collector(
    uow: UnitOfWork, fakes: Fakes, tmp_path: Path, clock: FakeClock
) -> Callable[[], RunService]:
    def restarted() -> RunService:
        return RunService(
            uow, fakes.ports, ProcessRegistry(), state_dir=tmp_path / "state", clock=clock
        )

    return restarted


async def test_a_build_run_that_committed_sends_its_newest_commit_to_the_checks(
    runs: RunService, committing: Fakes, facts: TicketFacts
) -> None:
    await _ended(runs, facts)

    assert committing.flow.calls == [("build", facts.id, "c2")]


async def test_a_build_run_that_committed_nothing_sets_nothing_off(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "exit 0"

    run = await _ended(runs, facts)

    assert fakes.flow.calls == []
    assert state_of(run) == "failed"
    assert fakes.tickets.events[-1][3]["reason"] == "Build produced no verifiable committed changes"


async def test_a_build_run_with_an_empty_commit_does_not_pass(
    runs: RunService, committing: Fakes, facts: TicketFacts
) -> None:
    committing.trees.same_content = True

    run = await _ended(runs, facts)

    assert state_of(run) == "failed"
    assert committing.flow.calls == []


async def test_commits_whose_branch_was_not_fetched_back_set_nothing_off(
    runs: RunService, committing: Fakes, facts: TicketFacts
) -> None:
    committing.trees.refusal = "the clone's branch does not build on the board's"

    await _ended(runs, facts)

    assert committing.flow.calls == []


async def test_an_ended_review_run_hands_its_head_to_the_review_decision(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "exit 0"

    run = await _ended(runs, facts, stage="review")

    assert fakes.flow.calls == [("review", facts.id, run.id, "head0")]


async def test_a_refused_review_decision_still_settles_the_run(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "exit 0"
    fakes.flow.error = ConflictError("no review submitted by the run")

    run = await _ended(runs, facts, stage="review")
    await runs.collect()

    assert run.settled_at is not None
    assert fakes.flow.calls == [("review", facts.id, run.id, "head0")]
    (event,) = [e for e in fakes.tickets.events if e[1] == "run.handoff_refused"]
    assert event[2] == run.id
    assert describe(event[1], event[3]) == (
        "Review handoff refused: no review submitted by the run"
    )


@pytest.mark.parametrize(
    "failure",
    [DatabaseBusyError("the verdict store is busy"), OSError("the verdict store is unavailable")],
)
async def test_a_transient_review_handoff_resumes_when_the_collector_restarts(
    runs: RunService,
    fakes: Fakes,
    facts: TicketFacts,
    restart_collector: Callable[[], RunService],
    failure: Exception,
) -> None:
    fakes.agents.script = "exit 0"
    fakes.flow.error = failure

    run = await _ended(runs, facts, stage="review")
    call = ("review", facts.id, run.id, "head0")

    assert run.exit_code == 0
    assert run.settled_at is None
    assert fakes.flow.calls == [call]
    assert all(event[1] != "run.handoff_refused" for event in fakes.tickets.events)

    fakes.flow.error = None
    restarted = restart_collector()
    await restarted.collect()
    await restarted.collect()

    assert (await restarted.get(run.id)).settled_at is not None
    assert fakes.flow.calls == [call, call]
    assert sum(event[1] == "run.ended" for event in fakes.tickets.events) == 1


async def test_a_stopped_review_run_decides_nothing(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.argv = ("/bin/sleep", "30")
    (run,) = (await runs.start(facts.id, stage="review", options=StartOptions())).runs

    await runs.stop(run.id)

    assert fakes.flow.calls == []
