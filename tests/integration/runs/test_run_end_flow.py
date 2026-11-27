"""What the end of a run sets off: a build's commits go to their checks, a review to its verdict."""

import asyncio

import pytest

from code_factory.platform.errors import ConflictError
from code_factory.runs.models import Run, StartOptions
from code_factory.runs.ports import TicketFacts
from code_factory.runs.rules.records import state_of
from code_factory.runs.service import RunService
from runs_fakes import Fakes


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

    assert run.settled_at is not None


async def test_a_stopped_review_run_decides_nothing(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.argv = ("/bin/sleep", "30")
    (run,) = (await runs.start(facts.id, stage="review", options=StartOptions())).runs

    await runs.stop(run.id)

    assert fakes.flow.calls == []
