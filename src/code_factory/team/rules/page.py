"""The Team page's one read: what needs the owner, what waits, who works, what merged today."""

from collections.abc import Sequence

from code_factory.team.models import (
    Also,
    Counts,
    Facts,
    Groups,
    Row,
    TeamNow,
    TicketFacts,
    Worker,
)
from code_factory.team.rules.rows import (
    Context,
    done_row,
    owner_row,
    place_of,
    ticket_wait,
)
from code_factory.team.rules.stages import peek, stage_times
from code_factory.team.rules.workers import ENDED_AFTER


def ended(worker: Worker, now: float) -> bool:
    """Whether a worker has gone quiet for good: it shows on no row.

    A session or a run ends that way however it stopped; a land job or a gate only once its
    process has ended, so a live one stays stale however long.
    """
    quiet = now - worker.last_event >= ENDED_AFTER
    return quiet and (worker.actor.kind in {"session", "agent", "reviewer"} or not worker.alive)


def stale(worker: Worker, now: float) -> bool:
    """Whether a worker's process has gone or it has been quiet past its own threshold."""
    return not worker.alive or now - worker.last_event > worker.stale_after


def _worker_row(context: Context, worker: Worker, state: str) -> Row:
    actor = worker.actor
    if worker.ticket is None:
        row = Row(
            key=worker.key,
            state=state,  # ty: ignore[invalid-argument-type]
            ticket=None,
            actor=actor,
            line=worker.line,
            since=worker.since,
            until=None,
            also=(),
            pull=None,
        )
    else:
        row = context.row(
            worker.key,
            state,  # ty: ignore[invalid-argument-type]
            (worker.repository, worker.ticket),
            actor,
            line=worker.line,
            since=worker.since,
        )
    return row


def _stale_row(context: Context, worker: Worker) -> Row:
    why = "no event since" if worker.alive else "its process has ended"
    row = _worker_row(context, worker, "stale")
    return row.model_copy(update={"line": f"{worker.line}; {why}", "since": worker.last_event})


def _oldest_first(rows: list[Row]) -> list[Row]:
    return sorted(rows, key=lambda row: (row.since, row.key))


def _also(row: Row) -> Also:
    return Also(state=row.state, actor=row.actor, line=row.line, since=row.since, until=row.until)


def once_per_ticket(lists: Sequence[Sequence[Row]]) -> list[list[Row]]:
    """Keep each ticket's first row reading the groups most urgent first.

    Every later row of the ticket becomes a second line of that one; a row on no ticket stays.
    """
    first: dict[tuple[str, str], tuple[int, int]] = {}
    kept: list[list[Row]] = [[] for _ in lists]
    for group, rows in enumerate(lists):
        for row in rows:
            place = place_of(row.ticket) if row.ticket else None
            if place is not None and place in first:
                at_group, at = first[place]
                held = kept[at_group][at]
                kept[at_group][at] = held.model_copy(update={"also": (*held.also, _also(row))})
                continue
            if place is not None:
                first[place] = (group, len(kept[group]))
            kept[group].append(row)
    return kept


def _busy(facts: Facts, ticket: TicketFacts) -> bool:
    """Whether a worker or an owner item already names the ticket."""
    place = place_of(ticket.reference)
    return any(
        not ended(w, facts.now) and w.ticket is not None and (w.repository, w.ticket) == place
        for w in facts.workers
    ) or any(place_of(item.ticket) == place for item in facts.owner)


def _group_rows(facts: Facts, context: Context) -> Groups:
    now = facts.now
    live = [w for w in facts.workers if not ended(w, now)]
    quiet = [w for w in live if stale(w, now)]
    active = [w for w in live if not stale(w, now)]
    owner_rows = [owner_row(context, item) for item in facts.owner]
    needs_you = [row for row in owner_rows if row.state != "stale"]
    stale_rows = [row for row in owner_rows if row.state == "stale"]
    stale_rows += [_stale_row(context, w) for w in quiet]
    working = [_worker_row(context, w, "working") for w in active if not w.waiting]
    waiting = [_worker_row(context, w, "waiting") for w in active if w.waiting]
    for ticket in facts.tickets:
        row = None if _busy(facts, ticket) else ticket_wait(context, ticket, now)
        if row is not None:
            waiting.append(row)
    done = [
        done_row(context, ticket, ticket.merged)
        for ticket in facts.tickets
        if ticket.merged is not None and ticket.merged >= facts.today
    ]
    lists = once_per_ticket(
        [
            _oldest_first(needs_you),
            _oldest_first(stale_rows),
            _oldest_first(waiting),
            _oldest_first(working),
            list(reversed(_oldest_first(done))),
        ]
    )
    need, stale_group, wait, work, finished = lists
    return Groups(
        needs_you=tuple(need),
        waiting=tuple(wait),
        working=tuple(work),
        done_today=tuple(finished),
        stale=tuple(stale_group),
    )


def assemble(facts: Facts) -> TeamNow:
    """The page's answer from what one read gathered."""
    context = Context(
        tickets={place_of(t.reference): t for t in facts.tickets},
        gates=frozenset(
            (w.repository, w.ticket)
            for w in facts.workers
            if w.actor.kind == "gate" and w.ticket is not None
        ),
    )
    groups = _group_rows(facts, context)
    stages = stage_times(facts.tickets, facts.today, facts.cycle.since)
    shown = (*groups.needs_you, *groups.waiting, *groups.working, *groups.done_today, *groups.stale)
    peeks = {
        f"{row.ticket.repository}/{row.ticket.id}": peek(
            context.tickets[place_of(row.ticket)], stages
        )
        for row in shown
        if row.ticket is not None and place_of(row.ticket) in context.tickets
    }
    working_agents = {
        w.actor.name
        for w in facts.workers
        if w.actor.kind in {"agent", "reviewer"} and not stale(w, facts.now)
    }
    free = [name for name in facts.agents if name not in working_agents]
    return TeamNow(
        now=facts.now,
        today=facts.today,
        cycle=facts.cycle,
        counts=Counts(
            needs_you=len(groups.needs_you),
            waiting=len(groups.waiting),
            working=len(groups.working),
            done_today=len(groups.done_today),
            stale=len(groups.stale),
        ),
        groups=groups,
        idle=tuple(name for name in free if name not in facts.paused),
        paused=tuple(name for name in free if name in facts.paused),
        stages=stages,
        peek=dict(sorted(peeks.items())),
    )
