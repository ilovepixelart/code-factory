"""Reading GitHub's answers about pull requests."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from code_factory.delivery.models import CHECKS_CONTEXT, Ci, PullReading, PullState

_RANK: dict[str, int] = {"none": 0, "passed": 1, "pending": 2, "failed": 3}
_TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
_PASSING_RUN = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def _outcome(entry: Mapping[str, Any]) -> str:
    if entry.get("__typename") == "StatusContext":
        state = entry.get("state")
        if state == "SUCCESS":
            return "passed"
        return "pending" if state in {"PENDING", "EXPECTED"} else "failed"
    if entry.get("status") != "COMPLETED":
        return "pending"
    return "passed" if entry.get("conclusion") in _PASSING_RUN else "failed"


def _worst(outcomes: list[str]) -> Ci:
    return max(outcomes, key=_RANK.__getitem__, default="none")  # ty: ignore[invalid-explicit-return]  # one of the four


def _reviewed(reviews: object) -> str:
    if not isinstance(reviews, list):
        return ""
    stamps = [
        str(r.get("submittedAt") or "")
        for r in reviews
        if isinstance(r, dict)
        and r.get("state") == "CHANGES_REQUESTED"
        and r.get("authorAssociation") in _TRUSTED
    ]
    return max(stamps, default="")


def _count(value: object) -> int | None:
    """A whole, non-negative count from GitHub's answer; anything else is unknown."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else None


def _review_time(review: object) -> datetime | None:
    """When a review by a trusted author was submitted; `None` for any other entry."""
    if (
        isinstance(review, dict)
        and review.get("authorAssociation") in _TRUSTED
        and review.get("state") in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED"}
    ):
        return _time(review.get("submittedAt"))
    return None


def _first_review(reviews: object) -> datetime | None:
    if not isinstance(reviews, list):
        return None
    return min((when for review in reviews if (when := _review_time(review))), default=None)


def reduce_pull(answer: Mapping[str, Any]) -> PullReading:
    """The pull request `gh pr view --json` describes, reduced to what the board keeps."""
    rollup = answer.get("statusCheckRollup")
    entries = [e for e in rollup if isinstance(e, dict)] if isinstance(rollup, list) else []
    ci = _worst([_outcome(e) for e in entries])
    others = [e for e in entries if e.get("context") != CHECKS_CONTEXT]
    own = [e for e in entries if e.get("context") == CHECKS_CONTEXT]
    other_ci = _worst([_outcome(e) for e in others]) if own else ci
    state = str(answer.get("state") or "").lower()
    return PullReading(
        state=state if state in {"open", "merged", "closed"} else "",
        review=str(answer.get("reviewDecision") or "").lower(),
        ci=ci,
        other_ci=other_ci if other_ci != ci else "",
        own_pending=any(_outcome(e) == "pending" for e in own),
        head=str(answer.get("headRefOid") or ""),
        base=str(answer.get("baseRefName") or ""),
        draft=answer.get("isDraft") is True,
        conflict=answer.get("mergeable") == "CONFLICTING",
        reviewed=_reviewed(answer.get("reviews")),
        merge_state=str(answer.get("mergeStateStatus") or ""),
        additions=_count(answer.get("additions")),
        deletions=_count(answer.get("deletions")),
        changed_files=_count(answer.get("changedFiles")),
        created_on_host=_time(answer.get("createdAt")),
        updated_on_host=_time(answer.get("updatedAt")),
        merged_on_host=_time(answer.get("mergedAt")),
        first_review_at=_first_review(answer.get("reviews")),
    )


def entered_since(
    last: tuple[PullState, str, str, datetime] | None, read: PullReading, now: datetime
) -> datetime:
    """When the pull request entered its (state, ci, head): kept while all three are unchanged."""
    if last is not None and last[:3] == (read.state, read.ci, read.head):
        return last[3]
    return now


def open_match(listed: object, base: str) -> tuple[str, str] | None:
    """The open pull request of this repository into `base`, as (url, head), from `gh pr list`."""
    if not isinstance(listed, list):
        return None
    for pull in listed:
        if (
            isinstance(pull, dict)
            and pull.get("isCrossRepository") is False
            and pull.get("baseRefName") == base
            and pull.get("url")
        ):
            return str(pull["url"]), str(pull.get("headRefOid") or "")
    return None
