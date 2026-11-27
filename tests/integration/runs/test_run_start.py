from datetime import timedelta
from pathlib import Path

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError, UnavailableError
from code_factory.runs.adapters.processes import ProcessRegistry
from code_factory.runs.models import StartOptions
from code_factory.runs.ports import Given, Settings, TicketFacts
from code_factory.runs.repository import HaltRepository, RunEnd, RunRepository
from code_factory.runs.service import RunService
from runs_fakes import Fakes
from runs_values import NOW, a_run, at


async def test_a_start_records_a_run_with_the_process_it_spawned(
    runs: RunService, facts: TicketFacts, tmp_path: Path
) -> None:
    started = await runs.start(facts.id)
    (run,) = started.runs
    assert (run.stage, run.agent, run.model, run.connection) == ("build", "writer", "m1", "c")
    assert run.ticket_id == facts.number
    assert run.ticket_key == facts.id
    assert run.repository == "sample"
    assert run.exit_code is None
    assert run.pid is not None
    assert run.pid_started_at is not None
    assert (run.head, run.instructions, run.memory_digest) == (
        "head0",
        "d1d1d1d1d1d1",
        "m3m3m3m3m3m3",
    )
    assert Path(run.worktree) == tmp_path / "tree-0"
    assert run.log == str(tmp_path / "state" / "runs" / f"{run.id}.log")
    assert len(run.id) == 12
    assert int(run.id, 16) >= 0


async def test_a_start_claims_then_probes_then_makes_the_tree_before_the_process(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    await runs.start(facts.id)
    assert fakes.calls.log == [
        f"claim:{facts.id}:build",
        "probe",
        "tree",
        "memory",
        "token",
        "launch",
        "attach",
        "event:run.started",
    ]


async def test_the_run_token_lives_as_long_as_the_run_may_plus_five_minutes(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.given_value = Given(
        agent="writer",
        runtime="claude",
        model="m1",
        connection="c",
        fingerprint="f1",
        max_seconds=100,
    )
    await runs.start(facts.id)
    await runs.start(facts.id, options=StartOptions(attempt=1))
    assert [t[4] for t in fakes.tokens.issued] == [400, 400]
    assert fakes.tokens.issued[0][1:4] == (facts.number, "build", "sample")
    assert [plan.timeout_s for plan in fakes.agents.plans] == [100, 100]


async def test_without_an_agent_limit_the_repositorys_run_timeout_sets_the_token_life(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.config.value = Settings(run_timeout_s=1200)
    await runs.start(facts.id)
    assert fakes.tokens.issued[0][4] == 1500
    assert fakes.agents.plans[0].timeout_s == 1200


async def test_the_run_is_announced_on_the_ticket(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    (run,) = (await runs.start(facts.id)).runs
    (_, kind, run_id, data) = fakes.tickets.events[0]
    assert (kind, run_id) == ("run.started", run.id)
    assert data["stage"] == "build"
    assert data["agent"] == "writer"


async def test_the_plan_the_agents_module_builds_the_command_from_names_the_run(
    runs: RunService, fakes: Fakes, facts: TicketFacts, tmp_path: Path
) -> None:
    (run,) = (
        await runs.start(facts.id, options=StartOptions(permissions="bypassPermissions"))
    ).runs
    (plan,) = fakes.agents.plans
    assert (plan.run_id, plan.stage, plan.permissions) == (run.id, "build", "bypassPermissions")
    assert plan.exit_file == tmp_path / "state" / "runs" / f"{run.id}.exit"
    assert plan.log == Path(run.log)
    assert plan.token == "tok-secret"  # noqa: S105
    assert "tok-secret" not in repr(plan)


async def test_a_start_is_refused_while_agents_are_halted(
    runs: RunService, fakes: Fakes, facts: TicketFacts, uow: UnitOfWork
) -> None:
    async with uow() as session:
        await HaltRepository(session).halt("owner", NOW)
    with pytest.raises(
        ConflictError,
        match="agents are stopped; resume them on the board or with code-factory resume",
    ):
        await runs.start(facts.id)
    assert fakes.calls.log == []


async def test_an_unknown_permission_mode_is_refused(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    with pytest.raises(BadRequestError, match="unknown permission mode"):
        await runs.start(facts.id, options=StartOptions(permissions="yolo"))
    assert fakes.calls.log == []


async def test_a_split_run_starts_only_with_the_prompt_the_split_command_gives(
    runs: RunService, facts: TicketFacts
) -> None:
    with pytest.raises(
        ConflictError,
        match="a split run starts only from code-factory split, which gives its prompt",
    ):
        await runs.start(facts.id, stage="split")
    started = await runs.start(facts.id, stage="split", options=StartOptions(prompt="split it"))
    assert started.runs[0].stage == "split"


async def test_a_merged_ticket_has_nothing_for_an_agent_to_do(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"column": "merged"})
    with pytest.raises(ConflictError, match="nothing for an agent to do at merged"):
        await runs.start(facts.id)
    assert fakes.calls.log == []


@pytest.mark.parametrize(
    ("blockers", "sentence"),
    [
        (("CF-7",), "blocked by CF-7, which is not done"),
        (("CF-7", "CF-8"), "blocked by CF-7, CF-8, which are not done"),
    ],
)
async def test_unfinished_blockers_refuse_a_start_with_their_ids(
    runs: RunService, fakes: Fakes, facts: TicketFacts, blockers: tuple[str, ...], sentence: str
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"blockers": blockers})
    with pytest.raises(ConflictError, match=sentence):
        await runs.start(facts.id)
    assert fakes.calls.log == []


async def test_the_default_stage_is_the_tickets_column(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"column": "spec"})
    (run,) = (await runs.start(facts.id)).runs
    assert run.stage == "spec"


async def test_a_claim_refusal_leaves_nothing_behind(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.teams.refusal = "CF-1 is claimed by another agent"
    with pytest.raises(ConflictError, match="claimed by another agent"):
        await runs.start(facts.id)
    assert await run_repo.active() == []
    assert fakes.calls.log == [f"claim:{facts.id}:build"]


async def test_a_failed_model_check_refuses_and_gives_the_claim_back(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.agents.given_value = fakes.agents.given_value.model_copy(
        update={"refusal": "agent writer: its model check failed"}
    )
    with pytest.raises(ConflictError, match="its model check failed"):
        await runs.start(facts.id)
    assert await run_repo.active() == []
    assert fakes.calls.log[-1] == "end_claim"
    assert "probe" not in fakes.calls.log


async def test_settings_that_changed_while_the_probe_waited_refuse_the_start(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.agents.changed_after_probe = fakes.agents.given_value.model_copy(
        update={"fingerprint": "f2"}
    )
    with pytest.raises(
        ConflictError,
        match="settings changed while the start waited on its model's server; start it again",
    ):
        await runs.start(facts.id)
    assert await run_repo.active() == []
    assert fakes.calls.log[-1] == "end_claim"
    assert "tree" not in fakes.calls.log


async def test_a_spent_ticket_budget_refuses_with_both_amounts(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"budget": "4"})
    await run_repo.insert(a_run(facts.number, "aaaaaaaaaaaa", cost=4.5, attempt=0))
    await run_repo.end("aaaaaaaaaaaa", RunEnd(exit_code=0, ended_at=at(1), cost=4.5))
    with pytest.raises(ConflictError, match=r"budget reached \(\$4\.50 of \$4\.00\)"):
        await runs.start(facts.id)
    assert fakes.calls.log[-1] == "end_claim"
    assert "tree" not in fakes.calls.log


async def test_a_spent_month_refuses_with_the_months_sentence(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.config.value = Settings(monthly_budget_usd=5.0)
    await run_repo.insert(
        a_run(
            None, "aaaaaaaaaaaa", stage="coordinate", cost=5.0, started_at=NOW - timedelta(days=1)
        )
    )
    with pytest.raises(
        ConflictError,
        match=r"the repository's budget for 2026-11 is reached \(\$5\.00 of \$5\.00\)",
    ):
        await runs.start(facts.id)


async def test_the_runs_cap_is_the_least_remainder_of_the_budgets(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"budget": "10"})
    fakes.config.value = Settings(monthly_budget_usd=5.0)
    await run_repo.insert(a_run(facts.number, "aaaaaaaaaaaa", attempt=0, cost=4.0))
    await run_repo.end("aaaaaaaaaaaa", RunEnd(exit_code=0, ended_at=at(1), cost=4.0))
    await runs.start(facts.id)
    assert fakes.agents.plans[0].remaining == pytest.approx(1.0)


async def test_a_tree_that_cannot_be_made_leaves_no_run_and_gives_the_claim_back(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.trees.fail_start = ConflictError("the tree is linked")
    with pytest.raises(ConflictError, match="the tree is linked"):
        await runs.start(facts.id)
    assert await run_repo.active() == []
    assert fakes.calls.log[-1] == "end_claim"


async def test_a_second_start_of_a_running_ticket_is_refused_and_the_first_run_goes_on(
    runs: RunService, facts: TicketFacts, run_repo: RunRepository
) -> None:
    (first,) = (await runs.start(facts.id)).runs
    with pytest.raises(ConflictError, match="an agent is already running on this ticket"):
        await runs.start(facts.id)
    assert [r.id for r in await run_repo.active()] == [first.id]


async def test_a_command_that_cannot_be_built_ends_the_run_unknown_and_gives_everything_back(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.agents.launch_error = UnavailableError(
        "the board could not find its own interpreter's path, so it starts no run"
    )
    with pytest.raises(UnavailableError, match="could not find its own interpreter's path"):
        await runs.start(facts.id)
    assert await run_repo.active() == []
    (ended,) = await run_repo.for_ticket(facts.number)
    assert ended.exit_code == -1
    assert "interpreter's path" in ended.halted
    assert fakes.calls.log[-2:] == ["revoke", "end_claim"]


async def test_a_board_that_cannot_launch_refuses_before_it_makes_the_tree(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.agents.refusal = "runs start only on a served board: run code-factory serve"

    with pytest.raises(UnavailableError, match="runs start only on a served board"):
        await runs.start(facts.id)

    assert "tree" not in fakes.calls.log
    assert await run_repo.for_ticket(facts.number) == []
    assert fakes.calls.log[-1] == "end_claim"


async def test_a_failed_start_removes_the_tree_it_made_and_the_branch_it_recorded(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.trees.made = True
    fakes.agents.launch_error = UnavailableError("no command")

    with pytest.raises(UnavailableError, match="no command"):
        await runs.start(facts.id)

    assert fakes.calls.log[-4:] == [
        "revoke",
        "remove_tree",
        f"clear_branch:{facts.id}",
        "end_claim",
    ]


async def test_a_failed_start_keeps_a_branch_the_ticket_had_before(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"branch": "feat/x"})
    fakes.trees.made = True
    fakes.agents.launch_error = UnavailableError("no command")

    with pytest.raises(UnavailableError, match="no command"):
        await runs.start(facts.id)

    assert fakes.calls.log[-3:] == ["revoke", "remove_tree", "end_claim"]


async def test_a_failed_start_leaves_a_tree_it_found(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.launch_error = UnavailableError("no command")

    with pytest.raises(UnavailableError, match="no command"):
        await runs.start(facts.id)

    assert "remove_tree" not in fakes.calls.log
    assert not any(c.startswith("clear_branch") for c in fakes.calls.log)


async def test_a_program_that_does_not_start_ends_the_run_unknown_with_its_token_revoked(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.agents.argv = ("/no/such/program",)
    with pytest.raises(UnavailableError, match="cannot start /no/such/program"):
        await runs.start(facts.id)
    (ended,) = await run_repo.for_ticket(facts.number)
    assert (ended.exit_code, ended.pid) == (-1, None)
    assert "revoke" in fakes.calls.log
    assert fakes.calls.log[-1] == "end_claim"
    assert "event:run.started" not in fakes.calls.log


async def test_a_failure_after_the_spawn_stops_the_process_and_undoes_the_start(
    runs: RunService,
    fakes: Fakes,
    facts: TicketFacts,
    run_repo: RunRepository,
    registry: ProcessRegistry,
) -> None:
    fakes.teams.attach_error = ConflictError("the claim is gone")
    with pytest.raises(ConflictError, match="the claim is gone"):
        await runs.start(facts.id)
    (ended,) = await run_repo.for_ticket(facts.number)
    assert (ended.exit_code, ended.halted) == (-1, "the claim is gone")
    assert ended.pid is not None
    assert registry.returncode(ended.pid) is not None
    assert fakes.calls.log[-2:] == ["revoke", "end_claim"]


async def test_a_failure_before_the_run_is_attached_gives_the_whole_claim_back(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.agents.launch_error = UnavailableError("no command")
    with pytest.raises(UnavailableError):
        await runs.start(facts.id)
    assert fakes.teams.ended_with == [None]


@pytest.fixture
def tickets_failing(fakes: Fakes) -> None:
    async def down(*_: object, **__: object) -> None:
        msg = "the ticket history is down"
        raise UnavailableError(msg)

    fakes.tickets.record_event = down


async def test_a_failure_after_the_run_is_attached_gives_back_the_claim_of_that_run(
    runs: RunService, fakes: Fakes, facts: TicketFacts, tickets_failing: None
) -> None:
    assert tickets_failing is None
    with pytest.raises(UnavailableError, match="the ticket history is down"):
        await runs.start(facts.id)
    (run_id,) = [e for e in fakes.teams.ended_with if e is not None]
    assert len(run_id) == 12


async def test_a_start_that_a_halt_ended_before_its_process_was_recorded_leaves_no_process(
    runs: RunService,
    fakes: Fakes,
    facts: TicketFacts,
    run_repo: RunRepository,
    registry: ProcessRegistry,
) -> None:
    async def halt_ends_the_row() -> None:
        (row,) = await run_repo.active()
        await run_repo.end(row.id, RunEnd(exit_code=-15, ended_at=NOW))

    fakes.agents.during_launch = halt_ends_the_row
    with pytest.raises(ConflictError, match="agents are stopped"):
        await runs.start(facts.id)
    (spawned,) = registry.pids()
    assert registry.returncode(spawned) is not None


async def test_a_process_whose_start_time_ps_cannot_read_still_has_its_pid_recorded(
    runs: RunService,
    facts: TicketFacts,
    registry: ProcessRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unreadable(pid: int) -> None:  # noqa: ARG001
        return None

    monkeypatch.setattr(registry._ps, "start_time", unreadable)  # the `ps` that failed
    (run,) = (await runs.start(facts.id)).runs
    assert run.pid in registry.pids()
    assert run.pid_started_at is None


async def test_parallel_attempts_start_one_run_each_under_one_claim_and_share_the_budget(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"parallel": "3", "budget": "10"})
    await run_repo.insert(a_run(facts.number, "aaaaaaaaaaaa", attempt=0, cost=4.0))
    await run_repo.end("aaaaaaaaaaaa", RunEnd(exit_code=0, ended_at=at(1), cost=4.0))
    started = await runs.start(facts.id)
    assert [run.attempt for run in started.runs] == [1, 2, 3]
    assert len({run.id for run in started.runs}) == 3
    assert fakes.calls.log.count(f"claim:{facts.id}:build") == 1
    assert [plan.remaining for plan in fakes.agents.plans] == [pytest.approx(2.0)] * 3
    assert [Path(run.worktree).name for run in started.runs] == ["tree-1", "tree-2", "tree-3"]


async def test_one_attempt_started_alone_shares_the_budget_by_the_attempt_count(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"parallel": "3", "budget": "6"})
    started = await runs.start(facts.id, options=StartOptions(attempt=2))
    assert [run.attempt for run in started.runs] == [2]
    assert fakes.agents.plans[0].remaining == pytest.approx(2.0)


async def test_attempts_are_started_for_a_build_only(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"parallel": "3"})
    started = await runs.start(facts.id, stage="spec")
    assert [run.attempt for run in started.runs] == [0]


async def test_a_later_attempt_that_fails_ends_only_itself_and_leaves_the_earlier_ones(
    runs: RunService,
    fakes: Fakes,
    facts: TicketFacts,
    run_repo: RunRepository,
    registry: ProcessRegistry,
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"parallel": "3"})
    fakes.trees.fail_attempt = 2
    fakes.trees.fail_start = UnavailableError("no room for a tree")
    with pytest.raises(UnavailableError, match="no room for a tree"):
        await runs.start(facts.id)
    active = await run_repo.active()
    assert [run.attempt for run in active] == [1]
    assert registry.returncode(active[0].pid or 0) is None
    assert "end_claim" not in fakes.calls.log


async def test_a_first_attempt_that_fails_gives_the_claim_back_and_starts_no_other(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    fakes.tickets.facts_by_id[facts.id] = facts.model_copy(update={"parallel": "3"})
    fakes.trees.fail_start = UnavailableError("no room for a tree")
    with pytest.raises(UnavailableError):
        await runs.start(facts.id)
    assert await run_repo.active() == []
    assert fakes.calls.log.count("end_claim") == 1
    assert fakes.calls.log.count("tree") == 1


async def test_a_ticket_ready_to_start_has_no_refusal(runs: RunService, facts: TicketFacts) -> None:
    assert await runs.start_refusal(facts.id) is None


async def test_the_refusal_names_a_halt_before_anything_else(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.teams.refusal = "the team has nobody for build"
    await runs.stop_all("cli")
    assert await runs.start_refusal(facts.id) == (
        "agents are stopped; resume them on the board or with code-factory resume"
    )


async def test_the_refusal_names_a_running_agent_before_the_teams_sentence(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    await runs.start(facts.id)
    fakes.teams.refusal = "the team has nobody for build"
    assert await runs.start_refusal(facts.id) == "an agent is already running on this ticket"


async def test_the_refusal_is_the_teams_sentence_for_the_stage_asked(
    runs: RunService, fakes: Fakes, facts: TicketFacts
) -> None:
    fakes.teams.refusal = "the team has nobody for review"
    assert await runs.start_refusal(facts.id, "review") == "the team has nobody for review"


async def test_asking_for_a_refusal_claims_and_starts_nothing(
    runs: RunService, fakes: Fakes, facts: TicketFacts, run_repo: RunRepository
) -> None:
    await runs.start_refusal(facts.id)
    assert fakes.calls.log == []
    assert await run_repo.active() == []
