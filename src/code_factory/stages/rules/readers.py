"""Readers over a ticket's activity: which run started after a record, what waits on the owner."""

from collections.abc import Sequence
from math import floor

from code_factory.stages.models import Record


def started_after(records: Sequence[Record], run_id: str, kind: str) -> bool:
    """Whether the run is the first to start after a record of `kind`.

    The last record before its `run.started` that is either one is of `kind`.
    """
    start = next(
        (at for at, r in enumerate(records) if r.kind == "run.started" and r.text("run") == run_id),
        None,
    )
    if start is None:
        return False
    previous = next((r for r in reversed(records[:start]) if r.kind in {kind, "run.started"}), None)
    return previous is not None and previous.kind == kind


def answered_before(answer: Record, started: float) -> bool:
    """Whether `answer` was recorded before a run that started at `started` (epoch seconds).

    In an earlier second: a stamp holds no fraction of one.
    """
    return floor(answer.at.timestamp()) < floor(started)


def answers_waiting(records: Sequence[Record]) -> list[Record]:
    """The owner's answers to be applied that no `answers_applied` record clears, oldest first.

    An answer recorded without `apply` waits for nothing.
    """

    def cleared(answer: Record) -> bool:
        return any(
            r.kind == "answers_applied"
            and isinstance(r.data.get("started"), int | float)
            and answered_before(answer, float(r.data["started"]))
            for r in records
        )

    return [
        r for r in records if r.kind == "answer" and r.data.get("apply") is True and not cleared(r)
    ]


def sent_back(records: Sequence[Record], tree: str) -> Record | None:
    """The latest time the owner sent the screens of `tree` back."""
    return next(
        (
            r
            for r in reversed(records)
            if r.kind == "capture_changes" and r.data.get("tree") == tree
        ),
        None,
    )


def waiting_capture(records: Sequence[Record], current: str) -> Record | None:
    """The latest capture when it shows the tree `current` and is neither approved nor sent back."""
    captured = next((r for r in reversed(records) if r.kind == "capture"), None)
    if captured is None or captured.data.get("tree") != current:
        return None
    approved = any(r.kind == "capture_approved" and r.data.get("tree") == current for r in records)
    return None if approved or sent_back(records, current) is not None else captured
