"""The parts of a card that derive from other modules' records."""

from pathlib import PurePosixPath
from typing import Any

from code_factory.board.models import ActivityRecord, CheckRecord, PullFacts, SessionFacts

# A run killed by the system or never started says nothing about the code.
NO_VERDICT_CODES = frozenset({137, -1})
OVERLAP_PREFIX = "next, "
_WORKTREES = (".code-factory", "worktrees")
_HIDDEN_EVENTS = frozenset({"branch_pushed", "merged_pull_request"})
_FAILURES = frozenset({"ship_failed", "merge_failed"})


def latest_check(
    records: list[CheckRecord], head: str, pull: PullFacts | None
) -> dict[str, Any] | None:
    """The newest check that judged `head` (any commit without a head), or None.

    `records` are oldest first. An open pull whose own check is pending shows none.
    """
    if pull is not None and pull.state == "open" and pull.own_pending:
        return None
    for record in reversed(records):
        if (head and record.commit != head) or record.exit_code in NO_VERDICT_CODES:
            continue
        return {"passed": record.exit_code == 0, "commit": record.commit}
    return None


def _event_applies(record: ActivityRecord, pull: PullFacts | None, head: str) -> bool:
    match record.kind:
        case "merge_failed":
            return (
                pull is not None
                and record.text("url") == pull.url
                and bool(head)
                and record.text("head") == head
            )
        case "ship_failed":
            return pull is None or not pull.url or (bool(head) and record.text("head") == head)
        case "ship_started" | "ship_pushed":
            return pull is None
        case "pull_request" | "branch_pushed" | "merged_pull_request":
            return True
        case _:
            return False


def delivery_event(
    records: list[ActivityRecord], pull: PullFacts | None, head: str
) -> dict[str, Any] | None:
    """The newest record that says where delivery stands, as `{kind, at, retry_at}`.

    A push or a merge is the newest word on a card that needs no event, so it hides the card's.
    """
    for record in reversed(records):
        if not _event_applies(record, pull, head):
            continue
        if record.kind in _HIDDEN_EVENTS:
            return None
        retry = record.data.get("retry_at")
        event: dict[str, Any] = {
            "kind": record.kind,
            "at": record.at,
            "retry_at": float(retry) if isinstance(retry, int | float) else None,
        }
        # A failure says why, in the words it was recorded with, so the ticket can show it.
        if record.kind in _FAILURES:
            event["reason"] = record.text("reason")
        return event
    return None


def _in_worktree(cwd: str, ticket_id: str) -> bool:
    parts = PurePosixPath(cwd).parts
    wanted = (*_WORKTREES, ticket_id)
    return any(parts[i : i + len(wanted)] == wanted for i in range(len(parts)))


def session_chips(
    sessions: list[SessionFacts], ticket_id: str, branch: str, default_branch: str
) -> list[dict[str, str]]:
    """The live sessions that work on a ticket: in its worktree, or on its own branch.

    The default branch belongs to no ticket, so a session on it never matches by branch.
    """
    own_branch = branch if branch and branch != default_branch else ""
    return [
        {"session_id": s.session_id, "state": s.state}
        for s in sessions
        if _in_worktree(s.cwd, ticket_id) or (own_branch and s.branch == own_branch)
    ]


def queue_fields(reason: str | None, holder: str | None) -> dict[str, str]:
    """`queue`, `overlap` and `holder`; a key with nothing to say is absent."""
    fields: dict[str, str] = {}
    if reason is not None:
        if reason.startswith(OVERLAP_PREFIX):
            fields["queue"] = "next"
            fields["overlap"] = reason.removeprefix(OVERLAP_PREFIX)
        else:
            fields["queue"] = reason or "next"
    if holder is not None and holder != "":
        fields["holder"] = holder
    return fields
