"""The pure rules of delivery: goldens of the previous implementation and hand-worked tables."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from code_factory.delivery.models import DeliveryEvent, LiveRead, MergeFacts, PullView
from code_factory.delivery.rules import (
    HEAD_MOVED,
    NO_SHIPPED,
    NOT_DEFAULT_BASE,
    NOT_READY,
    feedback_text,
    issue_of,
    merge_decision,
    next_retry,
    open_match,
    reduce_pull,
    settled,
    ship_due,
    status_body,
    triage,
)

CASES = json.loads((Path(__file__).parents[1] / "golden/formats/delivery/cases.json").read_text())
NOW = datetime(2026, 11, 1, tzinfo=UTC)
URL = "https://github.com/o/r/pull/7"


@pytest.mark.parametrize(
    ("answer", "expected"),
    list(zip(CASES["pulls"]["cases"], CASES["pulls"]["expected"], strict=True)),
)
def test_a_pull_answer_reduces_to_the_golden_card_fields(
    answer: dict[str, object], expected: dict[str, object]
) -> None:
    read = reduce_pull(answer)
    shown = {"state": read.state, "review": read.review, "ci": read.ci, "head": read.head}
    if read.draft:
        shown["draft"] = True
    assert shown == expected


@pytest.mark.parametrize(
    ("labels", "expected"),
    list(zip(CASES["triage"]["cases"], CASES["triage"]["expected"], strict=True)),
)
def test_triage_reads_type_and_priority_as_the_golden(
    labels: list[str], expected: list[str]
) -> None:
    assert list(triage(labels)) == expected


def test_the_boards_own_status_is_kept_apart_from_other_ci() -> None:
    read = reduce_pull(
        {
            "state": "OPEN",
            "statusCheckRollup": [
                {
                    "__typename": "StatusContext",
                    "context": "code-factory/checks",
                    "state": "PENDING",
                },
                {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"},
            ],
        }
    )
    assert (read.ci, read.other_ci, read.own_pending) == ("pending", "passed", True)


def test_only_an_associated_reviewers_changes_request_counts() -> None:
    reviews = [
        {"state": "CHANGES_REQUESTED", "authorAssociation": "NONE", "submittedAt": "2026-11-02"},
        {"state": "CHANGES_REQUESTED", "authorAssociation": "MEMBER", "submittedAt": "2026-11-01"},
    ]
    assert reduce_pull({"reviews": reviews}).reviewed == "2026-11-01"


def test_pull_attention_uses_the_first_submitted_maintainer_review_and_host_activity() -> None:
    read = reduce_pull(
        {
            "createdAt": "2026-10-31T00:00:00Z",
            "updatedAt": "2026-11-03T00:00:00Z",
            "reviews": [
                {
                    "state": "COMMENTED",
                    "authorAssociation": "NONE",
                    "submittedAt": "2026-10-31T01:00:00Z",
                },
                {
                    "state": "APPROVED",
                    "authorAssociation": "MEMBER",
                    "submittedAt": "2026-11-02T00:00:00Z",
                },
                {
                    "state": "COMMENTED",
                    "authorAssociation": "OWNER",
                    "submittedAt": "2026-11-01T00:00:00Z",
                },
            ],
        }
    )
    assert read.created_on_host == NOW - timedelta(days=1)
    assert read.first_review_at == NOW
    assert read.updated_on_host == NOW + timedelta(days=2)


def test_conflict_is_only_conflicting() -> None:
    assert reduce_pull({"mergeable": "CONFLICTING"}).conflict
    assert not reduce_pull({"mergeable": "UNKNOWN"}).conflict


@pytest.mark.parametrize(("attempts", "seconds"), [(0, 5), (1, 15), (2, 45)])
def test_a_transient_failure_retries_after_5_15_45_seconds(attempts: int, seconds: int) -> None:
    assert next_retry(attempts, "HTTP 502 Bad Gateway", NOW) == NOW + timedelta(seconds=seconds)


def test_a_fourth_attempt_and_a_permanent_reason_are_final() -> None:
    assert next_retry(3, "connection reset", NOW) is None
    assert next_retry(0, "Resource not accessible by integration", NOW) is None


def _failed(head: str, retry_at: datetime | None, kind: str = "ship_failed") -> DeliveryEvent:
    return DeliveryEvent(ticket_id="CF-1", kind=kind, head=head, url=URL, retry_at=retry_at, at=NOW)  # ty: ignore[invalid-argument-type]


def test_a_ship_waits_until_its_retry_time_and_a_final_failure_blocks_it() -> None:
    later = NOW + timedelta(seconds=5)
    assert not ship_due([_failed("a", later)], "a", NOW + timedelta(seconds=4))
    assert ship_due([_failed("a", later)], "a", later)
    assert not ship_due([_failed("a", None)], "a", NOW + timedelta(days=1))
    assert ship_due([_failed("a", None)], "b", NOW)


def test_a_final_refusal_settles_only_the_head_it_named() -> None:
    assert settled([_failed("a", None, "merge_failed")], URL, "a")
    assert not settled([_failed("a", None, "merge_failed")], URL, "b")
    assert not settled([_failed("a", NOW, "merge_failed")], URL, "a")


def test_open_match_takes_only_this_repositorys_pull_into_the_base() -> None:
    listed = [
        {"url": "u1", "headRefOid": "h1", "baseRefName": "main", "isCrossRepository": True},
        {"url": "u2", "headRefOid": "h2", "baseRefName": "dev", "isCrossRepository": False},
        {"url": "u3", "headRefOid": "h3", "baseRefName": "main", "isCrossRepository": False},
    ]
    assert open_match(listed, "main") == ("u3", "h3")
    assert open_match(listed[:2], "main") is None


def _pull(**changes: object) -> PullView:
    values: dict[str, object] = {
        "ticket_id": "CF-1", "repository": "r", "url": URL, "state": "open", "ci": "passed",
        "head": "abc", "base": "main", "shipped_head": "abc", "read_at": NOW, "since": NOW,
    }  # fmt: skip
    return PullView.model_validate(values | changes)


def _live(**changes: object) -> LiveRead:
    values: dict[str, object] = {
        "state": "OPEN",
        "base": "main",
        "head": "abc",
        "merge_state": "CLEAN",
    }
    return LiveRead.model_validate(values | changes)


def _facts(
    pull: PullView | None = None, live: LiveRead | None = None, **changes: object
) -> MergeFacts:
    values: dict[str, object] = {
        "pull": pull if pull is not None else _pull(), "default_branch": "main",
        "checks_configured": True, "checked": "passed", "live": live or _live(),
    }  # fmt: skip
    return MergeFacts.model_validate(values | changes)


def test_all_guards_holding_merge_with_the_match_head_argv() -> None:
    verdict = merge_decision(_facts())
    assert verdict.ready
    assert verdict.argv == ("pr", "merge", URL, "--merge", "--match-head-commit", "abc")


@pytest.mark.parametrize(
    ("facts", "reason"),
    [
        (_facts(pull=_pull(state="closed")), NOT_READY),
        (_facts(pull=_pull(draft=True)), NOT_READY),
        (_facts(pull=_pull(ci="failed")), NOT_READY),
        (_facts(pull=_pull(base="dev")), NOT_DEFAULT_BASE),
        (_facts(checked="missing"), "waits for the board's checks on abc"),
        (_facts(checked="failed"), "the board's checks failed on abc"),
        (_facts(pull=_pull(shipped_head="")), NO_SHIPPED),
        (_facts(pull=_pull(head="def")), HEAD_MOVED),
        (_facts(live=_live(head="def")), HEAD_MOVED),
        (
            _facts(live=_live(base="dev")),
            "the pull request merges into dev, not into main: the board merges only into main",
        ),
        (
            _facts(live=_live(merge_state="BLOCKED")),
            "GitHub does not call it mergeable yet: BLOCKED",
        ),
        (_facts(live=_live(draft=True)), NOT_READY),
    ],
)
def test_each_failing_guard_alone_refuses_with_its_sentence(facts: MergeFacts, reason: str) -> None:
    verdict = merge_decision(facts)
    assert (verdict.ready, verdict.reason) == (False, reason)


@pytest.mark.parametrize(
    "state", ["DIRTY", "UNKNOWN", "BLOCKED", "BEHIND", "UNSTABLE", "HAS_HOOKS"]
)
def test_only_clean_merges(state: str) -> None:
    assert not merge_decision(_facts(live=_live(merge_state=state))).ready


def test_no_checks_command_merges_without_a_verdict() -> None:
    assert merge_decision(_facts(checks_configured=False, checked="missing")).ready


def test_an_unreadable_live_base_is_recorded() -> None:
    verdict = merge_decision(_facts(live=_live(base_error="HTTP 502")))
    assert verdict.record_base_unread
    assert verdict.reason.endswith("not merged: HTTP 502")


def test_feedback_and_status_words() -> None:
    assert feedback_text("ci", URL, ["lint"], []).startswith(f"CI failed on {URL}: lint. Read")
    assert "see the review on GitHub" in feedback_text("review", URL, [], [])
    assert status_body("CF-3", "build", URL, waiting=True) == (
        f"Tracked as CF-3 in code-factory: Build. Pull request: {URL}. Waiting on the owner."
    )


def test_an_issue_must_belong_to_the_repository() -> None:
    assert issue_of("https://github.com/o/r/issues/12", "https://github.com/o/r")
    assert not issue_of("https://github.com/o/other/issues/12", "https://github.com/o/r")
    assert not issue_of("https://github.com/o/r/pull/12", "https://github.com/o/r")


# A pull request's size, as GitHub counts it, is kept so the board can say how much there is to
# review: the cost of reading a change grows with it while the cost of writing it does not.
def test_a_pull_answer_keeps_its_size() -> None:
    read = reduce_pull({"state": "OPEN", "additions": 120, "deletions": 30, "changedFiles": 4})
    assert (read.additions, read.deletions, read.changed_files) == (120, 30, 4)


@pytest.mark.parametrize("given", [None, "120", -1, True, 1.5])
def test_a_size_that_is_not_a_count_is_left_unknown(given: object) -> None:
    read = reduce_pull({"state": "OPEN", "additions": given, "deletions": 0, "changedFiles": 1})
    assert (read.additions, read.deletions) == (None, 0)


def test_the_card_carries_the_size_a_zero_included() -> None:
    card = _pull(additions=12, deletions=0, changed_files=1).as_card()
    unknown = _pull().as_card()
    assert (card["additions"], card["deletions"], card["changed_files"]) == (12, 0, 1)
    assert "additions" not in unknown
