"""One ticket's facts as the Team page reads them: milestones, pull request, waits, rows."""

from dataclasses import dataclass

from code_factory.team.models import (
    Actor,
    OwnerItem,
    PullState,
    Row,
    RowState,
    TeamActivity,
    TicketFacts,
    TicketRef,
)

CONFLICT_FILES = 3
Place = tuple[str, str]


def place_of(ticket: TicketRef) -> Place:
    """A ticket's key on the page: its repository and id."""
    return (ticket.repository, ticket.id)


def latest(ticket: TicketFacts, kind: str) -> TeamActivity | None:
    """The ticket's newest activity of `kind`."""
    return next((a for a in reversed(ticket.activities) if a.kind == kind), None)


def opening(ticket: TicketFacts) -> TeamActivity | None:
    """The first record of the pull request the latest record names (the rest only add a head)."""
    newest = latest(ticket, "pull_request")
    if newest is None:
        return None
    url = newest.text("url")
    return next(
        (a for a in ticket.activities if a.kind == "pull_request" and a.text("url") == url), None
    )


def pull_number(url: str) -> int:
    """The number a pull request's address ends with; 0 when it does not end with one."""
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    return int(tail) if tail.isascii() and tail.isdigit() else 0


def conflict_since(ticket: TicketFacts) -> float | None:
    """When the branch was last found conflicting, unless a gate run or pull request came later."""
    conflict = latest(ticket, "branch_conflict")
    if conflict is None:
        return None
    moved = any(
        a.kind in {"checks", "pull_request"} and a.at > conflict.at for a in ticket.activities
    )
    return None if moved else conflict.at


def conflict_line(ticket: TicketFacts) -> str:
    """The conflict's line, naming the first files its record keeps and how many more."""
    record = latest(ticket, "branch_conflict")
    files = [f for f in (record.text("files") if record else "").split(", ") if f]
    if not files:
        return "conflicts with main"
    named = ", ".join(files[:CONFLICT_FILES])
    more = len(files) - CONFLICT_FILES
    return (
        f"conflicts with main in {named} and {more} more"
        if more > 0
        else f"conflicts with main in {named}"
    )


def milestones(ticket: TicketFacts) -> tuple[float | None, ...]:
    """When the ticket was filed, committed, opened its pull request, passed the gate, merged."""
    created = next((a.at for a in ticket.activities if a.kind == "created"), None)
    passed = next(
        (a.at for a in ticket.activities if a.kind == "checks" and a.text("exit_code") == "0"), None
    )
    opened = opening(ticket)
    return (created, ticket.first_commit, opened.at if opened else None, passed, ticket.merged)


def pull_state(ticket: TicketFacts, gate_running: bool) -> PullState | None:
    """The row's pull request: its number, its gate and its merge state."""
    if ticket.pull is None:
        return None
    url, state = ticket.pull
    if state == "merged":
        merge = "merged"
    elif state == "open":
        merge = "conflict" if conflict_since(ticket) is not None else "open"
    else:
        return None
    if gate_running:
        gate = "running"
    elif ticket.check is None:
        gate = "not_run"
    else:
        gate = "passed" if ticket.check else "failed"
    return PullState(number=pull_number(url), url=url, gate=gate, merge=merge)


@dataclass(frozen=True, slots=True)
class Context:
    """What rows are built from: the tickets and which of them a gate runs on."""

    tickets: dict[Place, TicketFacts]
    gates: frozenset[Place]

    def row(  # noqa: PLR0913
        self,
        key: str,
        state: RowState,
        place: Place,
        actor: Actor,
        *,
        line: str = "",
        since: float = 0.0,
        until: float | None = None,
    ) -> Row:
        """A row on the ticket at `place`; a ticket the page does not know has an empty title."""
        found = self.tickets.get(place)
        reference = (
            found.reference if found else TicketRef(repository=place[0], id=place[1], title="")
        )
        pull = pull_state(found, place in self.gates) if found else None
        return Row(
            key=key,
            state=state,
            ticket=reference,
            actor=actor,
            line=line,
            since=since,
            until=until,
            also=(),
            pull=pull,
        )


def owner_row(context: Context, item: OwnerItem) -> Row:
    """What an inbox item waits for, in words; a stopped one is stale, the rest need the owner."""
    reason = item.reason
    state: RowState = "owner"
    if item.kind == "questions":
        line = f"{item.count} open question{'' if item.count == 1 else 's'}"
    elif item.kind == "screens":
        line = "screens wait for your approval"
    elif item.kind == "stopped":
        state, line = "stale", reason or "stopped"
    else:
        line = reason or item.kind
    ticket = item.ticket
    place = place_of(ticket)
    row = context.row(
        f"owner:{item.kind}:{ticket.repository}/{ticket.id}",
        state,
        place,
        Actor(kind="owner", name="you"),
        line=line,
        since=item.since,
    )
    return row if place in context.tickets else row.model_copy(update={"ticket": ticket})


def ticket_wait(context: Context, ticket: TicketFacts, now: float) -> Row | None:
    """A ticket in Review waiting on someone else: a conflict, review pickup or its pull request."""
    if ticket.column != "review":
        return None
    opened = opening(ticket)
    open_pull = ticket.pull if ticket.pull and ticket.pull[1] == "open" else None
    conflicted = conflict_since(ticket)
    if conflicted is not None:
        line, since, actor = (
            conflict_line(ticket),
            conflicted,
            Actor(kind="agent", name="build agent"),
        )
    elif open_pull is not None:
        started = opened.at if opened else ticket.column_since
        line = "waiting for a reviewer"
        since, actor = (
            (now if started is None else started),
            Actor(kind="reviewer", name="reviewer"),
        )
    elif ticket.pushed_without_pull:
        pushed = latest(ticket, "ship_pushed")
        started = pushed.at if pushed else ticket.column_since
        line = "branch pushed, no pull request yet"
        since, actor = (now if started is None else started), Actor(kind="board", name="board ship")
    else:
        return None
    ref = ticket.reference
    key = f"wait:{ref.repository}/{ref.id}"
    return context.row(key, "waiting", place_of(ref), actor, line=line, since=since)


def done_row(context: Context, ticket: TicketFacts, merged: float) -> Row:
    """A ticket merged today: since its filing, until its merge."""
    ref = ticket.reference
    filed = milestones(ticket)[0]
    return context.row(
        f"done:{ref.repository}/{ref.id}",
        "merged",
        place_of(ref),
        Actor(kind="board", name="merged"),
        since=merged if filed is None else filed,
        until=merged,
    )
