"""The fix loop after a pull request opens: what sends it back, rounds given and rounds out."""

from collections.abc import Callable, Sequence
from datetime import datetime

from code_factory.stages.models import (
    FixHalt,
    FixRound,
    PullView,
    Record,
    RoundOutcome,
)
from code_factory.stages.rules.checks import own_checks
from code_factory.stages.rules.logs import no_verdict

CONFLICT = "conflict"
SHORT = 12
LINE = 500


def feedback_reason(pull: PullView, own: int | None) -> str:
    """What sends an open pull request back: `ci`, `review`, or empty.

    The board's own checks are read from its record, never from the status it posts, which GitHub
    reports until its next read: of GitHub's CI only the checks that are not the board's count.
    Checks that gave no verdict are no failure of the code.
    """
    others = pull.other_ci or pull.ci
    failed = not pull.own_pending and own is not None and own != 0 and not no_verdict(own)
    if pull.state != "open":
        return ""
    if failed or others == "failed":
        return "ci"
    return "review" if pull.review == "changes_requested" else ""


def conflict_hold(records: Sequence[Record], tip: str) -> str:
    """Why a conflict holds the branch at `tip`; empty when none stands.

    The latest conflict record decides: a later `merge_conflict_cleared` ends it.
    """
    latest = next(
        (r for r in reversed(records) if r.kind in {"merge_conflict", "merge_conflict_cleared"}),
        None,
    )
    if latest is None or latest.kind != "merge_conflict" or latest.text("tip") != tip:
        return ""
    return f"conflicts with {latest.text('with')} in {latest.text('files')}"


def round_given(rounds: Sequence[FixRound], pull: PullView, reason: str) -> bool:
    """Whether a fix round for `reason` was given for what sends `pull` back.

    A review is told apart by when it was submitted, not by the head: GitHub keeps the decision on
    every later head until its author reads the fix. A round or a pull request that names no
    review counts for its head.
    """
    for given in rounds:
        if given.reason != reason:
            continue
        by_review = reason == "review" and bool(given.review) and bool(pull.reviewed)
        if (given.review == pull.reviewed) if by_review else (given.head == pull.head):
            return True
    return False


def _stands(
    halt: FixHalt, records: Sequence[Record], pull: PullView, *, failed: bool
) -> str | None:
    if halt.reason == "ci":
        return "" if failed else None
    if halt.reason == "review":
        return ": a review still requests changes" if pull.review == "changes_requested" else None
    if halt.reason == CONFLICT:
        hold = conflict_hold(records, pull.head)
        return f": {hold}" if hold else None
    return None


def rounds_out(halts: Sequence[FixHalt], records: Sequence[Record], pull: PullView) -> str | None:
    """What the owner is told once the rounds ran out on the head of the open pull request.

    Only while what the round was wanted for still stands there; `None` while rounds are left,
    or once nothing stands.
    """
    if pull.state != "open":
        return None
    found = own_checks(records, pull.head)
    failed = feedback_reason(pull, None if found is None else found[1]) == "ci"
    for halt in reversed(halts):
        if halt.head != pull.head:
            continue
        stands = _stands(halt, records, pull, failed=failed)
        if stands is not None:
            counted = "round" if halt.rounds == 1 else "rounds"
            return f"Fixes stopped after {halt.rounds} {counted}{stands}"
    return None


def halted_at(halts: Sequence[FixHalt], head: str) -> datetime | None:
    """When the ticket's fix rounds last ran out on `head`."""
    return next((halt.at for halt in reversed(halts) if halt.head == head), None)


def rounds_left(count: int, cap: int) -> int:
    """How many rounds a ticket may still be given."""
    return max(cap - count, 0)


def decide_round(count: int, cap: int, *, can_start: bool, given: bool) -> RoundOutcome:
    """`given` if the round exists, else `halted` at the cap, `waiting` with no start, `started`."""
    if given:
        return "given"
    if rounds_left(count, cap) == 0:
        return "halted"
    return "started" if can_start else "waiting"


def checks_task(
    head: str, code: int, steps: Sequence[str], lines: Sequence[str], mask: Callable[[str], str]
) -> str:
    """What the ticket's agent is told when the board's checks failed on `head`.

    A log is outside text and the task goes into a prompt that leaves the machine: each line is
    masked, then cut.
    """
    at = f" at {', '.join(steps)}" if steps else ""
    quoted = [mask(line)[:LINE] for line in lines]
    said = f"Their log says:\n{chr(10).join(quoted)}\n" if quoted else ""
    return (
        f"The board's checks failed on {head[:SHORT]}{at} (exit {code}). {said}"
        "Fix the cause on this branch, and keep every test green."
    )
