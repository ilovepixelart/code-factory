"""Who starts next: readiness, ordering and the caps that hold the rest."""

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from code_factory.follower.models import ActiveRunFact, Card, Planned
from code_factory.follower.rules.periods import retry_wait

PRIORITIES = ("urgent", "high", "medium", "low")
WORK_STAGES = {"spec", "build"}
_NATURAL = re.compile(r"(\d+)")
FAILURES_CAP = 5
NOT_STARTED = "not started: "
SPEC_NOT_READY = "spec not ready: "

Rule = Callable[[Card], str]


def due_for_review(stage: str, *, review_on: bool, last_stage: str | None) -> bool:
    """Whether a ticket in Review wants a review run: reviews are on and none ran since a build."""
    return stage == "review" and review_on and last_stage != "review"


def roles_due(configured: Sequence[str], runs: Sequence[tuple[str, datetime, bool]]) -> list[str]:
    """The review roles still to run before the review, in their configured order.

    `runs` are (stage, started at, succeeded) of the ticket's ended runs. A role is due until a
    run of it succeeds after the latest Build run started; a failed one is tried again.
    """
    builds = [started for stage, started, _ in runs if stage == "build"]
    since = max(builds) if builds else None
    done = {
        stage
        for stage, started, succeeded in runs
        if succeeded and (since is None or started >= since)
    }
    return [role for role in configured if role not in done]


def reader_due(
    runs: Sequence[tuple[str, datetime, bool]], *, spec_reader: bool, plan_critic: bool
) -> str:
    """The second reader a Build ticket wants before its next Build run, or empty.

    `read` once the Spec's documents are written and before the first Build run: due until a read
    succeeds after the latest Spec run started. `critique` once after a Build run ended, until one
    succeeds. `runs` are (stage, started at, succeeded) of the ticket's ended runs.
    """
    builds = [started for stage, started, _ in runs if stage == "build"]
    if spec_reader and not builds:
        specs = [started for stage, started, _ in runs if stage == "spec"]
        since = max(specs) if specs else None
        read = any(
            stage == "read" and ok and (since is None or started >= since)
            for stage, started, ok in runs
        )
        if not read:
            return "read"
    if plan_critic and builds and not any(s == "critique" and ok for s, _, ok in runs):
        return "critique"
    return ""


def due_for_fix(
    stage: str, returned_at: datetime | None, runs: Sequence[tuple[datetime, bool]]
) -> bool:
    """Whether a ticket a review returned to Build wants a fix run.

    `returned_at` is when the review returned it; `runs` are (started at, made commits) of its
    ended runs. Due until a run started after the return commits.
    """
    if stage != "build" or returned_at is None:
        return False
    return not any(started >= returned_at and committed for started, committed in runs)


def ready(card: Card) -> bool:
    """Whether the card may start: due work, nothing open that waits on someone."""
    due = card.review_due or card.fix_due or (card.stage in WORK_STAGES and not card.work_done)
    budget_left = card.budget is None or card.spent < card.budget
    return (
        not card.archived
        and due
        and card.runs == 0
        and card.unanswered == 0
        and not card.halted
        and not card.blocked
        and not card.open_blockers
        and budget_left
    )


def failure_streak(states: Sequence[str]) -> int:
    """How many of the newest ended runs failed in a row; `states` are newest first."""
    streak = 0
    for state in states:
        if state == "running":
            continue
        if state != "failed":
            break
        streak += 1
    return streak


def waiting(card: Card, now: datetime) -> str:
    """Why a due card waits on time or on the owner: a usage limit, a failure's wait, the cap."""
    if card.limited_until is not None and card.limited_until > now:
        return f"a usage limit holds it until {card.limited_until:%H:%M} UTC"
    if card.failures >= FAILURES_CAP:
        return (
            f"{NOT_STARTED}its last {card.failures} runs failed; "
            "start it by hand once the cause is fixed"
        )
    if card.failures and card.last_end is not None:
        due = card.last_end + retry_wait(card.failures)
        if due > now:
            runs = "run" if card.failures == 1 else "runs"
            return f"tried again at {due:%H:%M:%S} UTC, after {card.failures} failed {runs}"
    return ""


def spec_hold(card: Card) -> str:
    """Why a card due for its first Build run waits on its documents; empty when they are ready.

    A fix after a review, or a review, is not held: the spec was ready when Build began.
    """
    if card.stage != "build" or card.fix_due or card.review_due or not card.build_gaps:
        return ""
    return SPEC_NOT_READY + "; ".join(card.build_gaps)


def _natural(text: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part for part in _NATURAL.split(text))


def _order(card: Card) -> tuple[object, ...]:
    priority = PRIORITIES.index(card.priority) if card.priority in PRIORITIES else len(PRIORITIES)
    return (priority, not card.review_due, card.rank == 0, card.rank, _natural(card.id))


def _hold(  # noqa: PLR0913  # the counts each cap reads
    card: Card,
    *,
    used: Mapping[str, int],
    slots: Mapping[str, int],
    total: int,
    overall: int | None,
    columns: Mapping[str, int],
    limits: Mapping[str, int],
) -> str:
    room = slots.get(card.repository, 0)
    if used.get(card.repository, 0) >= room:
        return f"{card.repository} {used.get(card.repository, 0)} of {room}"
    if overall is not None and total >= overall:
        return f"all agents {total} of {overall}"
    limit = limits.get(card.stage)
    if limit is not None and columns.get(card.stage, 0) >= limit:
        return f"{card.stage.capitalize()} {columns.get(card.stage, 0)} of {limit}"
    return ""


def plan_queue(  # noqa: PLR0913  # the board's facts, all named
    cards: Sequence[Card],
    active: Sequence[ActiveRunFact],
    *,
    slots: Mapping[str, int],
    overall: int | None,
    limits: Mapping[str, int],
    rule: Rule | None = None,
    now: datetime | None = None,
) -> list[Planned]:
    """Ready cards in queue order, each with the first cap that holds it; a start counts.

    Given `now`, a card waiting on a usage limit or after failed runs is held by that first.
    """
    going = [run for run in active if run.active]
    running = {run.ticket_id for run in going}
    used: dict[str, int] = {}
    columns: dict[str, int] = {}
    for run in going:
        used[run.repository] = used.get(run.repository, 0) + 1
        columns[run.stage] = columns.get(run.stage, 0) + 1
    total = len(going)
    candidates = [
        c for c in cards if slots.get(c.repository, 0) > 0 and ready(c) and c.id not in running
    ]
    planned: list[Planned] = []
    for card in sorted(candidates, key=_order):
        reason = card.repair_hold or spec_hold(card) or ("" if now is None else waiting(card, now))
        reason = reason or _hold(
            card,
            used=used,
            slots=slots,
            total=total,
            overall=overall,
            columns=columns,
            limits=limits,
        )
        if not reason and rule is not None:
            reason = rule(card)
        if not reason:
            used[card.repository] = used.get(card.repository, 0) + 1
            columns[card.stage] = columns.get(card.stage, 0) + 1
            total += 1
        planned.append(Planned(id=card.id, reason=reason))
    return planned
