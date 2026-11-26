"""The card's check, delivery event, session chips and queue words."""

import pytest

from code_factory.board.models import ActivityRecord, CheckRecord, PullFacts, SessionFacts
from code_factory.board.rules.parts import (
    delivery_event,
    latest_check,
    queue_fields,
    session_chips,
)


def run(commit: str, code: int) -> CheckRecord:
    return CheckRecord(commit=commit, exit_code=code)


def test_the_newest_run_on_the_head_is_the_cards_check() -> None:
    records = [run("aaa", 1), run("aaa", 0), run("bbb", 1)]
    assert latest_check(records, "aaa", None) == {"passed": True, "commit": "aaa"}


def test_a_run_that_gave_no_verdict_is_not_the_cards_check() -> None:
    records = [run("aaa", 1), run("aaa", 0), run("aaa", 137)]
    assert latest_check(records, "aaa", None) == {"passed": True, "commit": "aaa"}
    records = [run("aaa", 1), run("aaa", 0), run("aaa", -1)]
    assert latest_check(records, "aaa", None) == {"passed": True, "commit": "aaa"}


def test_only_no_verdict_runs_leave_no_check() -> None:
    assert latest_check([run("aaa", 137)], "aaa", None) is None


def test_a_new_head_clears_the_previous_check() -> None:
    assert latest_check([run("aaa", 0)], "bbb", None) is None


def test_without_a_head_the_newest_run_of_any_commit_counts() -> None:
    assert latest_check([run("aaa", 0), run("bbb", 1)], "", None) == {
        "passed": False,
        "commit": "bbb",
    }


def test_an_open_pull_with_a_pending_own_check_hides_the_previous_failure() -> None:
    pull = PullFacts(state="open", own_pending=True)
    assert latest_check([run("aaa", 1)], "aaa", pull) is None


def test_a_pending_check_on_a_closed_pull_hides_nothing() -> None:
    pull = PullFacts(state="closed", own_pending=True)
    assert latest_check([run("aaa", 1)], "aaa", pull) == {"passed": False, "commit": "aaa"}


def rec(kind: str, at: float = 1.0, **data: object) -> ActivityRecord:
    return ActivityRecord(kind=kind, at=at, data=data)


PULL = PullFacts(url="https://x/pull/1", head="h1")


def test_a_pull_request_record_is_the_delivery_event() -> None:
    assert delivery_event([rec("pull_request", 1789871400.0)], PULL, "h1") == {
        "kind": "pull_request",
        "at": 1789871400.0,
        "retry_at": None,
    }


def test_the_newest_matching_record_wins() -> None:
    records = [rec("pull_request", 1.0), rec("ship_failed", 2.0, head="h1", retry_at=9.0)]
    assert delivery_event(records, PULL, "h1") == {
        "kind": "ship_failed",
        "at": 2.0,
        "retry_at": 9.0,
        "reason": "",
    }


@pytest.mark.parametrize(
    ("record", "shown"),
    [
        (rec("merge_failed", url="https://x/pull/1", head="h1"), True),
        (rec("merge_failed", url="https://x/pull/2", head="h1"), False),
        (rec("merge_failed", url="https://x/pull/1", head="h0"), False),
        (rec("ship_failed", head="h1"), True),
        (rec("ship_failed", head="h0"), False),
        (rec("ship_started"), False),
        (rec("ship_pushed"), False),
    ],
)
def test_a_failure_shows_only_for_the_pull_and_head_it_names(
    record: ActivityRecord, shown: bool
) -> None:
    assert (delivery_event([record], PULL, "h1") is not None) is shown


@pytest.mark.parametrize(
    ("record", "pull"),
    [
        (rec("ship_failed", 3.0, head="h1", reason="push rejected (non-fast-forward)"), None),
        (
            rec(
                "merge_failed",
                3.0,
                url="https://x/pull/1",
                head="h1",
                reason="push rejected (non-fast-forward)",
            ),
            PULL,
        ),
    ],
)
def test_a_failure_names_the_reason_it_was_recorded_with(
    record: ActivityRecord, pull: PullFacts | None
) -> None:
    assert delivery_event([record], pull, "h1") == {
        "kind": record.kind,
        "at": 3.0,
        "retry_at": None,
        "reason": "push rejected (non-fast-forward)",
    }


def test_a_ship_failure_shows_when_there_is_no_pull() -> None:
    assert delivery_event([rec("ship_failed", head="zzz")], None, "h1") is not None


def test_ship_started_shows_only_before_a_pull_exists() -> None:
    assert delivery_event([rec("ship_started")], None, "h1") == {
        "kind": "ship_started",
        "at": 1.0,
        "retry_at": None,
    }


@pytest.mark.parametrize("kind", ["branch_pushed", "merged_pull_request"])
def test_a_push_or_a_merge_hides_the_event(kind: str) -> None:
    assert delivery_event([rec("pull_request"), rec(kind, 2.0)], PULL, "h1") is None


def test_an_unrelated_record_is_no_event() -> None:
    assert delivery_event([rec("note")], PULL, "h1") is None


def view(cwd: str, branch: str = "other", sid: str = "s1") -> SessionFacts:
    return SessionFacts(session_id=sid, cwd=cwd, branch=branch, state="idle")


def test_a_session_in_the_tickets_worktree_is_its_chip() -> None:
    sessions = [view("/x/.code-factory/worktrees/CF-1/src")]
    assert session_chips(sessions, "CF-1", "", "main") == [{"session_id": "s1", "state": "idle"}]


def test_a_worktree_of_a_ticket_with_the_same_prefix_is_not_a_match() -> None:
    assert session_chips([view("/x/.code-factory/worktrees/CF-10")], "CF-1", "", "main") == []


def test_the_worktree_must_be_whole_path_components() -> None:
    assert session_chips([view("/x/.code-factory/worktrees-CF-1")], "CF-1", "", "main") == []


def test_a_session_on_the_tickets_own_branch_is_its_chip() -> None:
    sessions = [view("/elsewhere", branch="feat/CF-2")]
    assert len(session_chips(sessions, "CF-2", "feat/CF-2", "main")) == 1


def test_the_default_branch_belongs_to_no_ticket() -> None:
    assert session_chips([view("/elsewhere", branch="main")], "CF-3", "main", "main") == []


def test_a_ticket_without_a_branch_matches_no_session_by_branch() -> None:
    assert session_chips([view("/elsewhere", branch="")], "CF-3", "", "main") == []


def test_an_overlap_reason_is_next_with_the_overlap() -> None:
    assert queue_fields("next, touches CF-4", None) == {"queue": "next", "overlap": "touches CF-4"}


def test_an_empty_reason_is_next() -> None:
    assert queue_fields("", None) == {"queue": "next"}


def test_another_reason_is_shown_as_it_is() -> None:
    assert queue_fields("waits for a slot", "claude") == {
        "queue": "waits for a slot",
        "holder": "claude",
    }


def test_no_plan_and_no_holder_leave_no_keys() -> None:
    assert queue_fields(None, None) == {}


def test_an_empty_holder_is_not_a_holder() -> None:
    assert queue_fields(None, "") == {}
