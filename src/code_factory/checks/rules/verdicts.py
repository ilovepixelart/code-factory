"""The commit status, the judged exit, the sleep excuse and the ledger record of a run."""

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from code_factory.checks.models import NO_VERDICT_CODES, Judged
from code_factory.stages.models import LogReading

CONTAINER_UNAVAILABLE = "checks container unavailable"
CONTAINER_NOT_STARTED = "gate: the checks container could not start: no verdict"
MOVED = "gate: the tree changed while the checks ran: no verdict on the commit it began on"


def _code_of(record: Mapping[str, Any]) -> int | None:
    code = record.get("exit_code")
    return code if isinstance(code, int) and not isinstance(code, bool) else None


def status_for(record: Mapping[str, Any]) -> tuple[str, str] | None:
    """The commit status a `checks` record posts: its state and description, or None.

    A record with no commit has nothing to post on. No verdict (-1, 137) is pending, not a
    failure: the checks run again.
    """
    if not record.get("commit"):
        return None
    code = _code_of(record)
    if code == 0:
        return "success", "The board's checks passed"
    if code in NO_VERDICT_CODES:
        if record.get("reason") == CONTAINER_UNAVAILABLE:
            return "pending", "The checks container could not start"
        return "pending", "The board's checks gave no verdict and run again"
    exited = "did not run" if code is None else f"exited {code}"
    return "failure", f"The board's checks failed: {exited}"


def judged_exit(before: Judged, after: Judged, code: int) -> tuple[int, bool]:
    """The code to record and whether the tree moved: no verdict (-1) when it did.

    Only the commit and the tracked files count: a file the command created is not the commit's.
    """
    held = (before.head, before.tracked, before.tree_id) == (
        after.head,
        after.tracked,
        after.tree_id,
    )
    return (code, False) if held else (-1, True)


def slept_between(before: str | None, after: str | None, code: int) -> bool:
    """Whether a failed run is excused by the machine sleeping: both readings differ."""
    return code != 0 and before is not None and after is not None and before != after


def _named(pairs: list[tuple[str, int]]) -> dict[str, int]:
    return dict(pairs)


def checks_record(  # noqa: PLR0913  # the facts of one record, named by the caller
    judged: Judged,
    code: int,
    log: str,
    reading: LogReading | None,
    *,
    slept: bool = False,
    text: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The `checks` record of a run.

    `reading` is what the stages module reads from the log; None when it could not be read, which
    marks the record `log_unread`. `text` is the log itself, for the container line.
    """
    data: dict[str, Any] = {
        "commit": judged.head,
        "exit_code": code,
        "log": log,
        "tree": judged.tree,
    }
    if judged.tree_id:
        data["tree_id"] = judged.tree_id
    if slept:
        data["slept"] = True
    data.update(extra or {})
    if reading is None:
        data["log_unread"] = True
        return data
    lines = (text or "").splitlines()
    if code == -1 and CONTAINER_NOT_STARTED in lines:
        data["reason"] = CONTAINER_UNAVAILABLE
    elif code > 0 and reading.failure_reason:
        data["reason"] = reading.failure_reason
    if reading.flaky_steps:
        data["retried"] = list(reading.flaky_steps)
    if reading.reported_steps:
        data["steps"] = dict(reading.reported_steps)
    for key, pairs in (
        ("seconds", reading.step_seconds),
        ("lock_waits", reading.lock_waits),
        ("quarantined", reading.quarantined_failures),
    ):
        if pairs:
            data[key] = _named(pairs)
    return data


def clean_log_tail(text: str) -> str:
    """`text` without control characters but a tab and a newline (a runner's log is not trusted)."""
    return "".join(char for char in text if char.isprintable() or char in "\n\t")


def verdict_for(
    records: Sequence[Mapping[str, Any]], head: str, tree_id: str
) -> Literal["passed", "failed", "missing"]:
    """What the board's checks say of `head`, from `checks` records newest first.

    Only the newest record of that commit counts, and only when it names a tree id equal to
    `tree_id`: a pass on another tree, or on a tree nobody named, says nothing of this one. A
    killed attempt, a run of another scope (`fast`, `full`: not the command the gate asks for) and
    a run with no verdict (-1, 137) or no code say nothing either.
    """
    found = next(
        (
            record
            for record in records
            if record.get("commit") == head
            and record.get("outcome") != "killed"
            and record.get("scope", "reached") == "reached"
        ),
        None,
    )
    if found is None or not tree_id or found.get("tree_id") != tree_id:
        return "missing"
    code = _code_of(found)
    if code is None or code in NO_VERDICT_CODES:
        return "missing"
    return "passed" if code == 0 else "failed"
