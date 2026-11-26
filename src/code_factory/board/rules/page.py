"""The ticket page parts: time in columns, the folded activity, capture, conflict and proof."""

from datetime import datetime
from typing import Any

from code_factory.platform.text import section_rows
from code_factory.tickets.models import ActivityEntry

PAGE_COLUMNS = ("spec", "build", "review")
ACCEPTANCE = "## Acceptance criteria"
REVIEW_CHECK = "review"
_CRITERION_CELLS = 3


def stage_timeline(entries: list[ActivityEntry]) -> list[tuple[datetime, str]]:
    """Where the ticket was and since when: spec from its creation, then each recorded move."""
    timeline: list[tuple[datetime, str]] = []
    for item in entries:
        if item.kind == "created":
            timeline.append((item.at, "spec"))
        elif item.kind == "stage" and item.data.get("to"):
            timeline.append((item.at, str(item.data["to"])))
    return timeline


def time_in_stages(timeline: list[tuple[datetime, str]], now: datetime) -> dict[str, int]:
    """Whole seconds in each stage, in the order first entered; the current stage runs to `now`."""
    spent: dict[str, int] = {}
    for index, (start, stage) in enumerate(timeline):
        end = timeline[index + 1][0] if index + 1 < len(timeline) else now
        seconds = max(0, int((end - start).total_seconds()))
        spent[stage] = spent.get(stage, 0) + seconds
    return spent


def column_seconds(entries: list[ActivityEntry], now: datetime) -> dict[str, int | None]:
    """The seconds in spec, build and review; None for a column the ticket never entered."""
    spent = time_in_stages(stage_timeline(entries), now)
    return {column: spent.get(column) for column in PAGE_COLUMNS}


def _text(item: ActivityEntry, key: str) -> str:
    value = item.data.get(key)
    return "" if value is None else str(value)


def _outcome(end: ActivityEntry | None) -> str:
    if end is None:
        return "running"
    if end.data.get("stopped"):
        return "stopped"
    if end.data.get("exit_code") != 0:
        return "failed"
    return "uncommitted" if end.data.get("uncommitted") else "finished"


def _run_entry(start: ActivityEntry, end: ActivityEntry | None) -> dict[str, Any]:
    def either(key: str) -> str:
        ended = _text(end, key) if end else ""
        return ended or _text(start, key)

    def ended(key: str) -> Any:  # noqa: ANN401
        return end.data.get(key) if end else None

    return {
        "at": start.at.timestamp(),
        "kind": "run",
        "run": _text(start, "run"),
        "agent": either("agent"),
        "model": either("model"),
        "stage": _text(start, "stage"),
        "iteration": start.data.get("iteration", 1),
        "outcome": _outcome(end),
        "exit_code": ended("exit_code"),
        "duration": ended("duration"),
        "tokens": ended("tokens"),
        "sentence": (end or start).sentence,
        "text": either("reason"),
    }


def _plain_entry(item: ActivityEntry) -> dict[str, Any]:
    shown: dict[str, Any] = {
        "at": item.at.timestamp(),
        "sentence": item.sentence,
        "kind": item.kind,
        "text": _text(item, "text"),
    }
    if item.kind == "coordinator_edit":
        shown["edit"] = {key: _text(item, key) for key in ("name", "from", "to")}
    if item.kind.startswith("run.") and _text(item, "run"):
        shown["run"] = _text(item, "run")
    return shown


def fold_activity(entries: list[ActivityEntry]) -> list[dict[str, Any]]:
    """The page's activity, newest first: a run's start and end are one entry.

    `entries` are oldest first. A run end whose start is not among them stays an entry of its own.
    """
    ends = {_text(e, "run"): e for e in entries if e.kind == "run.ended" and _text(e, "run")}
    started = {_text(e, "run") for e in entries if e.kind == "run.started"}
    page: list[dict[str, Any]] = []
    for item in reversed(entries):
        if item.kind == "run.ended" and _text(item, "run") in started:
            continue
        if item.kind == "run.started" and _text(item, "run"):
            page.append(_run_entry(item, ends.get(_text(item, "run"))))
        else:
            page.append(_plain_entry(item))
    return page


def _latest(entries: list[ActivityEntry], *kinds: str) -> ActivityEntry | None:
    return next((e for e in reversed(entries) if e.kind in kinds), None)


def capture_state(entries: list[ActivityEntry]) -> dict[str, Any] | None:
    """The latest capture and what the newest answer on its tree made of it."""
    shot = _latest(entries, "capture")
    if shot is None:
        return None
    tree = _text(shot, "tree")
    found: dict[str, Any] = {"tree": tree, "images": shot.data.get("images", []), "state": "waits"}
    answer = next(
        (
            e
            for e in reversed(entries)
            if e.kind in {"capture_approved", "capture_changes"} and _text(e, "tree") == tree
        ),
        None,
    )
    if answer is not None and answer.kind == "capture_approved":
        found |= {"state": "approved", "by": _text(answer, "by")}
    elif answer is not None:
        found |= {"state": "sent_back", "reason": _text(answer, "reason")}
    return found


def conflict_of(entries: list[ActivityEntry], tip: str) -> dict[str, str]:
    """The merge conflict standing on `tip`, or the tip alone: a later clearing ends a conflict."""
    newest = _latest(entries, "branch_conflict", "branch_conflict_cleared")
    if newest is None or newest.kind != "branch_conflict" or _text(newest, "tip") != tip:
        return {"tip": tip}
    return {"tip": tip, "with": _text(newest, "with"), "files": _text(newest, "files")}


def _not_proven(requirements: str) -> list[str]:
    return [
        f"{row.cells[0]}: {row.cells[1]}"
        for row in section_rows(requirements, ACCEPTANCE)
        if len(row.cells) >= _CRITERION_CELLS and row.cells[-1].strip("`") == REVIEW_CHECK
    ]


def _approved(entries: list[ActivityEntry], tree: str) -> bool:
    return any(e.kind == "capture_approved" and _text(e, "tree") == tree for e in entries)


def evidence_summary(
    entries: list[ActivityEntry], verdict: str, requirements: str
) -> dict[str, Any]:
    """What the ticket proved: its latest gate run, the review verdict, its capture, the rest."""
    check = _latest(entries, "checks")
    shot = capture_state(entries)
    return {
        "gate": None
        if check is None
        else {
            "held": check.data.get("exit_code") == 0,
            "commit": _text(check, "commit"),
            "tree": _text(check, "tree"),
        },
        "verdict": verdict,
        "capture": None
        if shot is None
        else {"tree": shot["tree"], "approved": _approved(entries, shot["tree"])},
        "not_proven": _not_proven(requirements),
    }
