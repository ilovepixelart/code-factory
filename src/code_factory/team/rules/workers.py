"""The workers the Team page lists: runs, gates, the board's ship and land jobs, subagents."""

from code_factory.team.models import (
    ActiveRun,
    Actor,
    AtWork,
    LandJob,
    RunningGate,
    TicketFacts,
    Worker,
)
from code_factory.team.rules.gate import gate_line, gate_progress

STALE_AFTER = 600.0
ENDED_AFTER = 3600.0
_SHIP_ENDS = {"pull_request", "branch_pushed", "ship_failed"}

# A review and the review roles before it read the work; the rest write it.
REVIEWING = frozenset({"review", "qa", "security", "tests", "read", "critique"})


def run_worker(active: ActiveRun, now: float) -> Worker:
    """A run recorded running; its heartbeat is `now` while its process lives."""
    run = active.run
    return Worker(
        key=f"run:{run.id}",
        repository=run.repository,
        ticket=run.ticket_id,
        actor=Actor(
            kind="reviewer" if run.stage in REVIEWING else "agent", name=run.agent or "default"
        ),
        line=f"{run.stage} run",
        since=run.started_at,
        last_event=now if active.alive else run.started_at,
        alive=active.alive,
        stale_after=STALE_AFTER,
    )


def gate_worker(gate: RunningGate) -> Worker:
    """A gate running on a ticket's tree; it is stale past its step's longest pass plus 600 s."""
    progress = gate_progress(gate.log, gate.lock, gate.tree)
    step_longest = gate.longest.get(progress.step or "", max(gate.longest.values(), default=0.0))
    return Worker(
        key=f"gate:{gate.repository}/{gate.ticket_id}",
        repository=gate.repository,
        ticket=gate.ticket_id,
        actor=Actor(kind="gate", name="gate"),
        line=gate_line(progress),
        since=gate.written_at if progress.waiting else gate.started_at,
        last_event=gate.written_at,
        alive=True,
        stale_after=step_longest + STALE_AFTER,
        waiting=progress.waiting,
    )


def land_worker(job: LandJob, repository: str, now: float) -> Worker:
    """A land job recorded running."""
    return Worker(
        key=f"land:{job.ticket_id}:{job.started_at:.3f}",
        repository=repository,
        ticket=job.ticket_id,
        actor=Actor(kind="board", name="board land"),
        line="landing",
        since=job.started_at,
        last_event=now if job.alive else job.started_at,
        alive=job.alive,
        stale_after=STALE_AFTER,
    )


def session_worker(at_work: AtWork, repository: str) -> Worker:
    """A running subagent of a session; its process is the session's, so it always lives."""
    return Worker(
        key=f"session:{at_work.agent_id}",
        repository=repository,
        ticket=at_work.ticket_id,
        actor=Actor(kind=at_work.kind, name=at_work.name),  # ty: ignore[invalid-argument-type]
        line=at_work.doing,
        since=at_work.since,
        last_event=at_work.last_event_at,
        alive=True,
        stale_after=STALE_AFTER,
    )


def ship_worker(ticket: TicketFacts, now: float) -> Worker | None:
    """The board's ship of the ticket's branch while its latest start has no end after it.

    The board records no heartbeat while it ships, so a start with no end is stale once older
    than 600 s and on no row once older than 3600 s.
    """
    index = next(
        (
            i
            for i in range(len(ticket.activities) - 1, -1, -1)
            if ticket.activities[i].kind == "ship_started"
        ),
        None,
    )
    if index is None:
        return None
    since = ticket.activities[index].at
    after = ticket.activities[index + 1 :]
    if any(a.kind in _SHIP_ENDS for a in after) or now - since >= ENDED_AFTER:
        return None
    pushed = any(a.kind == "ship_pushed" for a in after)
    ref = ticket.reference
    return Worker(
        key=f"ship:{ref.repository}/{ref.id}",
        repository=ref.repository,
        ticket=ref.id,
        actor=Actor(kind="board", name="board ship"),
        line="branch pushed, opening its pull request" if pushed else "pushing the branch",
        since=since,
        last_event=since,
        alive=True,
        stale_after=STALE_AFTER,
    )
