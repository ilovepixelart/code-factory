"""The workers the page lists, built from what the runs, checks, sessions and jobs modules say."""

from code_factory.team.models import ActiveRun, AtWork, LandJob, RunningGate
from code_factory.team.rules import gate_worker, land_worker, run_worker, session_worker
from team_page_values import MINUTE, NOW
from team_values import run

LOG = "gate: preflight passed in 1s\ngate: rust-lint starts\n"


def test_a_run_whose_process_lives_is_heard_from_now_and_one_whose_process_is_gone_is_not() -> None:
    live = run_worker(ActiveRun(run=run("r1", agent="builder", started=NOW - 90), alive=True), NOW)
    gone = run_worker(ActiveRun(run=run("r1", agent="builder", started=NOW - 90), alive=False), NOW)
    assert (live.key, live.last_event, live.alive, live.since) == ("run:r1", NOW, True, NOW - 90)
    assert (gone.last_event, gone.alive) == (NOW - 90, False)
    assert (live.actor.kind, live.actor.name, live.line, live.ticket) == (
        "agent",
        "builder",
        "build run",
        "CF-1",
    )


def test_a_review_run_is_a_reviewer_and_a_run_of_no_agent_is_the_default() -> None:
    worker = run_worker(ActiveRun(run=run("r2", stage="review"), alive=True), NOW)
    assert (worker.actor.kind, worker.actor.name, worker.line) == (
        "reviewer",
        "default",
        "review run",
    )


def test_a_gate_is_stale_past_its_steps_longest_pass_plus_600_seconds() -> None:
    gate = RunningGate(
        repository="sample",
        ticket_id="CF-3",
        tree="/t/CF-3",
        started_at=NOW - 500,
        written_at=NOW - 20,
        log=LOG,
        longest={"rust-lint": 120.0, "rust-test": 900.0},
    )
    worker = gate_worker(gate)
    assert (worker.key, worker.line, worker.stale_after, worker.since) == (
        "gate:sample/CF-3",
        "rust-lint",
        720.0,
        NOW - 500,
    )
    assert (worker.last_event, worker.waiting, worker.actor.kind) == (NOW - 20, False, "gate")


def test_a_gate_in_a_step_with_no_recorded_pass_uses_the_longest_of_any_step() -> None:
    gate = RunningGate(
        repository="sample",
        ticket_id="CF-3",
        tree="/t/CF-3",
        started_at=NOW - 500,
        written_at=NOW - 20,
        log=LOG,
        longest={"rust-test": 900.0},
    )
    assert gate_worker(gate).stale_after == 1500.0
    bare = gate.model_copy(update={"longest": {}})
    assert gate_worker(bare).stale_after == 600.0


def test_a_gate_waiting_for_the_lock_is_a_waiting_worker_since_its_log_last_grew() -> None:
    log = (
        "gate: rust-lint waits for the heavy-step lock, held by pid 7: rust-test in /t/CF-6 on b\n"
    )
    gate = RunningGate(
        repository="sample",
        ticket_id="CF-3",
        tree="/t/CF-3",
        started_at=NOW - 500,
        written_at=NOW - 4 * MINUTE,
        log=log,
    )
    worker = gate_worker(gate)
    assert (worker.waiting, worker.since, worker.line) == (
        True,
        NOW - 4 * MINUTE,
        "waiting for the heavy-step lock behind CF-6 (rust-test)",
    )


def test_a_land_job_and_a_subagent_become_workers_on_their_ticket() -> None:
    land = land_worker(LandJob(ticket_id="CF-5", started_at=NOW - 30, alive=False), "api", NOW)
    assert (land.repository, land.ticket, land.line, land.alive, land.last_event) == (
        "api",
        "CF-5",
        "landing",
        False,
        NOW - 30,
    )
    assert (land.actor.kind, land.actor.name) == ("board", "board land")
    alive = land_worker(LandJob(ticket_id="CF-5", started_at=NOW - 30, alive=True), "api", NOW)
    assert alive.last_event == NOW
    at_work = AtWork(
        agent_id="a1",
        ticket_id="CF-9",
        kind="session",
        name="ticket-worker 54f2",
        doing="Edit a.rs",
        since=NOW - 60,
        last_event_at=NOW - 5,
    )
    sub = session_worker(at_work, "api")
    assert (sub.key, sub.repository, sub.ticket, sub.line, sub.alive, sub.last_event) == (
        "session:a1",
        "api",
        "CF-9",
        "Edit a.rs",
        True,
        NOW - 5,
    )
    assert (sub.actor.kind, sub.actor.name, sub.stale_after) == (
        "session",
        "ticket-worker 54f2",
        600.0,
    )
