"""The board's checks on a branch head: attempts, failed steps, and whether main fails too."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from code_factory.stages.models import MainCheckView, Record
from code_factory.stages.rules.logs import CONTAINER_UNAVAILABLE, no_verdict

RUNS = 2
RETRY_AFTER = timedelta(seconds=60)


def exit_code_of(record: Record) -> int | None:
    """The record's exit code when it holds a whole number."""
    code = record.data.get("exit_code")
    return code if isinstance(code, int) and not isinstance(code, bool) else None


def own_checks(records: Sequence[Record], head: str) -> tuple[Record, int] | None:
    """The board's latest checks on `head` and their exit code; `None` with none."""
    latest = next(
        (
            r
            for r in reversed(records)
            if r.kind == "checks" and r.text("commit") == head and r.text("scope") != "fast"
        ),
        None,
    )
    code = None if latest is None else exit_code_of(latest)
    return None if latest is None or code is None else (latest, code)


def attempts_of(records: Sequence[Record], head: str) -> tuple[bool, int, int]:
    """`(passed, failed, interrupted)` of the checks tied to the head's tree.

    Consecutive interruptions have their own count, reset by any verdict, so an infrastructure
    failure cannot spend the retry a test failure gets.
    """
    passed, failed, interrupted = False, 0, 0
    for record in records:
        code = exit_code_of(record)
        counts = (
            record.kind == "checks"
            and record.text("commit") == head
            and record.text("scope") != "fast"
            and bool(record.text("tree_id"))
            and record.text("reason") != CONTAINER_UNAVAILABLE
        )
        if code is None or not counts:
            continue
        if no_verdict(code):
            interrupted += 1
        else:
            interrupted = 0
            passed = passed or code == 0
            failed += code != 0
    return passed, failed, interrupted


def settled(records: Sequence[Record], head: str) -> bool:
    """Whether the checks passed, failed twice, or were interrupted twice in a row on the head."""
    passed, failed, interrupted = attempts_of(records, head)
    return passed or failed >= RUNS or interrupted >= RUNS


def rerun_pending(records: Sequence[Record], head: str) -> bool:
    """Whether the checks failed once on the head and their one rerun has not run."""
    failed = attempts_of(records, head)[1]
    return failed == 1 and not settled(records, head)


def container_retry_due(records: Sequence[Record], head: str, now: datetime) -> bool:
    """Whether the head's checks may run again: a minute after its container was unavailable."""
    found = own_checks(records, head)
    if found is None:
        return True
    check, code = found
    if not no_verdict(code) or check.text("reason") != CONTAINER_UNAVAILABLE:
        return True
    return now >= check.at + RETRY_AFTER


def failed_steps(check: Record) -> list[str]:
    """The steps a `checks` record reports failed."""
    steps = check.data.get("steps")
    if not isinstance(steps, dict):
        return []
    return [str(step) for step, state in steps.items() if state == "failed"]


def fails_on_main(
    steps: Sequence[str], tests: Sequence[str], main: MainCheckView, main_tests: Sequence[str]
) -> str | None:
    """The step on which main's run failed with the same failing tests as the head's checks.

    A step the head's checks report failed that main's run failed too, the tests each log names
    equal. `None` when main's run passed or gave no verdict, or failed another step.
    """
    if not main.failed or no_verdict(main.exit_code) or list(tests) != list(main_tests):
        return None
    return next((step for step in steps if step == main.step), None)


def waits_on_main(step: str) -> str:
    """What the ticket's status says while its pull request waits for main."""
    return f"Fails on main too at {step}"
