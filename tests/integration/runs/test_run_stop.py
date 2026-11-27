"""Stopping one run or every run, and the halt that keeps agents from starting."""

import asyncio
import signal

import pytest

from code_factory.platform.errors import ConflictError, NotFoundError
from code_factory.runs.adapters.processes import ProcessRegistry, Target
from code_factory.runs.models import Run, StartOptions
from code_factory.runs.ports import TicketFacts
from code_factory.runs.repository import RunRepository
from code_factory.runs.service import RunService
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService
from runs_fakes import Fakes
from runs_values import NOW, OWNER, a_run


async def started(runs: RunService, facts: TicketFacts, *, looping: bool = False) -> Run:
    options = StartOptions(looping=looping)
    return (await runs.start(facts.id, options=options)).runs[0]


async def alive(registry: ProcessRegistry, run: Run) -> bool:
    assert run.pid is not None
    return registry.returncode(run.pid) is None


async def test_stopping_a_run_ends_its_group_and_records_a_stop(
    runs: RunService, fakes: Fakes, facts: TicketFacts, registry: ProcessRegistry
) -> None:
    fakes.agents.script = "sleep 30"
    run = await started(runs, facts, looping=True)
    assert run.looping is True
    for _ in range(100):  # the wrapper handles SIGTERM once it runs
        await asyncio.sleep(0.05)
        if registry.returncode(run.pid or 0) is None and runs.log_path(run.id).exists():
            break
    await asyncio.sleep(0.5)
    stopped = await runs.stop(run.id)
    assert stopped.exit_code == -signal.SIGTERM
    assert stopped.looping is False
    assert not await alive(registry, run)
    assert stopped.settled_at is not None
    ended = [e for e in fakes.tickets.events if e[1] == "run.ended"]
    assert len(ended) == 1
    assert ended[0][3]["stopped"] is True
    assert "save" in fakes.calls.log
    assert fakes.calls.log.count("revoke") == 1


async def test_stopping_an_ended_run_returns_it_unchanged(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "exit 0"
    run = await started(runs, facts)
    for _ in range(100):
        if runs.exit_path(run.id).exists():
            break
        await asyncio.sleep(0.05)
    (ended,) = await runs.collect()
    again = await runs.stop(run.id)
    assert again == ended.run
    assert fakes.calls.log.count("revoke") == 1


async def test_stopping_an_unknown_run_says_so(runs: RunService) -> None:
    with pytest.raises(NotFoundError, match="no such run"):
        await runs.stop("000000000000")


async def test_a_redirected_tree_is_the_reason_a_stopped_run_records(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "sleep 30"
    fakes.trees.redirected = "the tree's git folder is not the one the board made"
    run = await started(runs, facts)
    stopped = await runs.stop(run.id)
    assert stopped.halted == "the tree's git folder is not the one the board made"


async def test_a_halt_stops_a_run_and_records_why(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "sleep 30"
    run = await started(runs, facts)
    assert await runs.halt_run(run.id, "stopped at its cap: 5000 tokens") is True
    kept = await runs.get(run.id)
    assert kept.halted == "stopped at its cap: 5000 tokens"
    assert kept.exit_code is not None


async def test_halting_a_run_that_is_unknown_or_ended_is_false(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    assert await runs.halt_run("000000000000", "why") is False
    fakes.agents.script = "exit 0"
    run = await started(runs, facts)
    for _ in range(100):
        if runs.exit_path(run.id).exists():
            break
        await asyncio.sleep(0.05)
    await runs.collect()
    assert await runs.halt_run(run.id, "why") is False


async def test_stopping_every_agent_holds_them_first_and_ends_every_run(
    runs: RunService,
    fakes: Fakes,
    facts: TicketFacts,
    tickets: TicketService,
    registry: ProcessRegistry,
) -> None:
    fakes.agents.script = "sleep 30"
    first = await started(runs, facts)
    other = await tickets.create(
        NewTicket(repository="sample", title="B"),
        by=OWNER,
    )
    fakes.tickets.facts_by_id[other.id] = facts.model_copy(
        update={"id": other.id, "number": other.number}
    )
    second = (await runs.start(other.id)).runs[0]
    stopped = await runs.stop_all("cli")
    assert sorted(stopped) == sorted([first.id, second.id])
    assert await runs.halted_at() is not None
    with pytest.raises(ConflictError, match="agents are stopped"):
        await runs.start(facts.id)
    assert not await alive(registry, first)
    assert not await alive(registry, second)


async def test_resume_lets_agents_start_and_is_idempotent(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "sleep 30"
    await runs.stop_all("cli")
    await runs.resume()
    await runs.resume()
    assert await runs.halted_at() is None
    assert (await runs.start(facts.id)).runs


async def test_stopping_every_agent_with_none_running_still_holds_them(runs: RunService) -> None:
    assert await runs.stop_all("cli") == []
    assert await runs.halted_at() is not None


async def test_stopping_a_run_that_has_no_process_ends_it_at_once(
    runs: RunService, facts: TicketFacts, run_repo: RunRepository
) -> None:
    await run_repo.insert(a_run(facts.number, "aaaaaaaaaaaa", started_at=NOW))
    stopped = await runs.stop("aaaaaaaaaaaa")
    assert stopped.exit_code == -signal.SIGTERM


async def test_a_collection_that_fails_does_not_keep_halt_from_stopping_the_runs(
    runs: RunService,
    fakes: Fakes,
    facts: TicketFacts,
    registry: ProcessRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fakes.agents.script = "sleep 30"
    run = await started(runs, facts)

    async def failing(now: object = None) -> list[object]:  # noqa: ARG001
        msg = "the checkout cannot be read"
        raise RuntimeError(msg)

    monkeypatch.setattr(runs, "collect", failing)
    assert await runs.stop_all("cli") == [run.id]
    assert not await alive(registry, run)


async def test_a_stop_whose_checkout_cannot_be_read_still_ends_the_run_with_the_reason(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "sleep 30"
    redirected = "the tree's git folder is not the one the board made"
    fakes.trees.redirected = redirected
    run = await started(runs, facts)
    fakes.trees.head_error = ConflictError(redirected)
    stopped = await runs.stop(run.id)
    assert stopped.exit_code == -signal.SIGTERM
    assert stopped.halted == redirected
    assert stopped.settled_at is not None


async def test_commits_the_main_checkout_cannot_read_yet_are_recorded_as_unknown(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.script = "sleep 30"
    run = await started(runs, facts)
    fakes.trees.heads = ["head9"]
    fakes.trees.commits_error = ConflictError("bad object head9")
    stopped = await runs.stop(run.id)
    assert stopped.exit_code == -signal.SIGTERM
    assert stopped.commits is None


async def test_a_halt_stops_every_active_run_at_the_same_time(
    runs: RunService,
    fakes: Fakes,
    facts: TicketFacts,
    registry: ProcessRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fakes.agents.script = "sleep 30"
    first = await started(runs, facts)
    other = await runs.start(facts.id, options=StartOptions(attempt=1))
    in_flight = peak = 0
    real_stop = registry.stop

    async def counting(target: Target) -> None:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.1)  # long enough for the other stop to begin
        await real_stop(target)
        in_flight -= 1

    monkeypatch.setattr(registry, "stop", counting)
    stopped = await runs.stop_all("cli")
    assert sorted(stopped) == sorted([first.id, other.runs[0].id])
    assert peak == 2


async def test_a_stop_whose_tree_record_is_gone_still_ends_the_run(
    runs: RunService, fakes: Fakes, facts: TicketFacts, registry: ProcessRegistry
) -> None:
    fakes.agents.script = "sleep 30"
    run = await started(runs, facts)
    fakes.trees.redirection_error = NotFoundError("no tree cf-1 is recorded for sample")
    stopped = await runs.stop(run.id)
    assert stopped.exit_code == -signal.SIGTERM
    assert stopped.settled_at is not None
    assert not await alive(registry, run)
