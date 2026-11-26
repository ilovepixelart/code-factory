"""The ticket page's derived parts, worked by hand from the records they read."""

from datetime import UTC, datetime, timedelta
from typing import Any

from code_factory.board.rules.page import (
    capture_state,
    column_seconds,
    conflict_of,
    evidence_summary,
    fold_activity,
    stage_timeline,
    time_in_stages,
)
from code_factory.tickets.models import ActivityEntry

T0 = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)


def entry(kind: str, seconds: float = 0, sentence: str = "", **data: Any) -> ActivityEntry:  # noqa: ANN401
    return ActivityEntry(
        at=T0 + timedelta(seconds=seconds), kind=kind, by="x", sentence=sentence or kind, data=data
    )


def test_a_ticket_is_in_spec_from_its_creation_and_moves_by_its_stage_records() -> None:
    entries = [entry("created", 0), entry("stage", 100, to="build"), entry("note", 120)]
    assert stage_timeline(entries) == [(T0, "spec"), (T0 + timedelta(seconds=100), "build")]


def test_a_stage_record_without_a_target_is_no_move() -> None:
    assert stage_timeline([entry("created"), entry("stage", 5, to="")]) == [(T0, "spec")]


def test_repeated_stages_are_summed_in_the_order_first_entered() -> None:
    timeline = [
        (T0, "spec"),
        (T0 + timedelta(seconds=100), "build"),
        (T0 + timedelta(seconds=150), "spec"),
    ]
    spent = time_in_stages(timeline, T0 + timedelta(seconds=160))
    assert spent == {"spec": 110, "build": 50}
    assert list(spent) == ["spec", "build"]


def test_a_span_that_runs_backwards_counts_zero() -> None:
    timeline = [(T0 + timedelta(seconds=50), "spec"), (T0, "build")]
    assert time_in_stages(timeline, T0 + timedelta(seconds=10)) == {"spec": 0, "build": 10}


def test_the_page_names_spec_build_and_review_and_nulls_a_column_never_entered() -> None:
    entries = [entry("created", 0), entry("stage", 100, to="build")]
    assert column_seconds(entries, T0 + timedelta(seconds=130)) == {
        "spec": 100,
        "build": 30,
        "review": None,
    }


def test_the_activity_is_newest_first_in_the_page_shape() -> None:
    entries = [
        entry("created", 1, "Created as a bug"),
        entry("note", 2, "alex left a note", text="hello"),
    ]
    assert fold_activity(entries) == [
        {"at": T0.timestamp() + 2, "sentence": "alex left a note", "kind": "note", "text": "hello"},
        {"at": T0.timestamp() + 1, "sentence": "Created as a bug", "kind": "created", "text": ""},
    ]


def run_start(seconds: float = 10, **data: Any) -> ActivityEntry:  # noqa: ANN401
    return entry("run.started", seconds, "Agent started", run="r1", stage="build", **data)


def test_a_started_run_with_no_end_is_running() -> None:
    [folded] = fold_activity([run_start(agent="claude", model="m1")])
    assert folded == {
        "at": T0.timestamp() + 10,
        "kind": "run",
        "run": "r1",
        "agent": "claude",
        "model": "m1",
        "stage": "build",
        "iteration": 1,
        "outcome": "running",
        "exit_code": None,
        "duration": None,
        "tokens": None,
        "sentence": "Agent started",
        "text": "",
    }


def test_a_run_and_its_end_are_one_entry_that_takes_the_ends_facts() -> None:
    end = entry(
        "run.ended",
        70,
        "Agent finished",
        run="r1",
        exit_code=0,
        duration=60,
        tokens=900,
        model="m2",
    )
    folded = fold_activity([run_start(iteration=3, agent="claude", model="m1"), end])
    assert len(folded) == 1
    assert (folded[0]["outcome"], folded[0]["model"], folded[0]["iteration"]) == (
        "finished",
        "m2",
        3,
    )
    assert (folded[0]["exit_code"], folded[0]["duration"], folded[0]["tokens"]) == (0, 60, 900)
    assert folded[0]["sentence"] == "Agent finished"
    assert folded[0]["at"] == T0.timestamp() + 10


def test_a_run_end_takes_its_agent_from_the_start_when_it_names_none() -> None:
    end = entry("run.ended", 70, run="r1", exit_code=0)
    assert fold_activity([run_start(agent="claude"), end])[0]["agent"] == "claude"


def outcome_of(**end: Any) -> str:  # noqa: ANN401
    folded = fold_activity([run_start(), entry("run.ended", 70, run="r1", **end)])
    return str(folded[0]["outcome"])


def test_how_a_run_ended_is_stopped_then_failed_then_uncommitted_then_finished() -> None:
    assert outcome_of(stopped=True, exit_code=1) == "stopped"
    assert outcome_of(exit_code=1, uncommitted=True) == "failed"
    assert outcome_of(exit_code=0, uncommitted=True) == "uncommitted"
    assert outcome_of(exit_code=0) == "finished"
    assert outcome_of() == "failed"


def test_a_run_end_with_no_start_stays_a_plain_entry_that_names_its_run() -> None:
    [folded] = fold_activity([entry("run.ended", 70, "Agent finished", run="r9", exit_code=0)])
    assert folded == {
        "at": T0.timestamp() + 70,
        "sentence": "Agent finished",
        "kind": "run.ended",
        "text": "",
        "run": "r9",
    }


def test_a_coordinator_edit_carries_what_it_changed() -> None:
    edit = entry("coordinator_edit", 3, "set", name="rank", **{"from": 1, "to": 2})
    assert fold_activity([edit])[0]["edit"] == {"name": "rank", "from": "1", "to": "2"}


def test_the_latest_capture_waits_until_an_answer_names_its_tree() -> None:
    entries = [entry("capture", 1, tree="t1", images=["a.png"])]
    assert capture_state(entries) == {"tree": "t1", "images": ["a.png"], "state": "waits"}


def test_an_approval_of_the_tree_approves_it_and_names_who() -> None:
    entries = [entry("capture", 1, tree="t1"), entry("capture_approved", 2, tree="t1", by="alex")]
    assert capture_state(entries) == {
        "tree": "t1",
        "images": [],
        "state": "approved",
        "by": "alex",
    }


def test_sending_a_capture_back_names_the_reason() -> None:
    entries = [
        entry("capture", 1, tree="t2"),
        entry("capture_changes", 2, tree="t2", reason="blurry"),
    ]
    assert capture_state(entries) == {
        "tree": "t2",
        "images": [],
        "state": "sent_back",
        "reason": "blurry",
    }


def test_an_answer_to_another_tree_does_not_count() -> None:
    entries = [entry("capture", 1, tree="t2"), entry("capture_approved", 2, tree="t1", by="a")]
    assert capture_state(entries) == {"tree": "t2", "images": [], "state": "waits"}


def test_no_capture_is_none() -> None:
    assert capture_state([entry("note")]) is None


def test_a_conflict_stands_while_no_later_check_cleared_it() -> None:
    entries = [entry("branch_conflict", 1, tip="abc", **{"with": "main"}, files="a.py")]
    assert conflict_of(entries, "abc") == {"tip": "abc", "with": "main", "files": "a.py"}


def test_a_cleared_conflict_or_another_tip_is_the_tip_alone() -> None:
    cleared = [
        entry("branch_conflict", 1, tip="abc"),
        entry("branch_conflict_cleared", 2, tip="abc"),
    ]
    assert conflict_of(cleared, "abc") == {"tip": "abc"}
    assert conflict_of([entry("branch_conflict", 1, tip="abc")], "def") == {"tip": "def"}


REQUIREMENTS = """# FRD

## Acceptance criteria

| ID | Criterion | Check |
|----|-----------|-------|
| CF-1-A1 | It shows | `review` |
| CF-1-A2 | It counts | test_counts |
| CF-1-A3 | It reads well | review |
| CF-1-A4 | review |
"""


def test_the_gate_the_verdict_the_capture_and_what_only_review_checks() -> None:
    entries = [
        entry("checks", 1, commit="abc", exit_code=1, tree="t0"),
        entry("checks", 2, commit="def", exit_code=0, tree="t1"),
        entry("capture", 3, tree="t1"),
        entry("capture_approved", 4, tree="t1", by="alex"),
    ]
    assert evidence_summary(entries, "pass", REQUIREMENTS) == {
        "gate": {"held": True, "commit": "def", "tree": "t1"},
        "verdict": "pass",
        "capture": {"tree": "t1", "approved": True},
        "not_proven": ["CF-1-A1: It shows", "CF-1-A3: It reads well"],
    }


def test_a_ticket_with_no_records_proves_nothing() -> None:
    assert evidence_summary([], "", "") == {
        "gate": None,
        "verdict": "",
        "capture": None,
        "not_proven": [],
    }


def test_a_failed_gate_is_not_held() -> None:
    summary = evidence_summary([entry("checks", 1, commit="a", exit_code=2)], "", "")
    assert summary["gate"] == {"held": False, "commit": "a", "tree": ""}


def test_a_capture_approved_on_another_tree_is_not_an_approval_in_the_summary() -> None:
    entries = [entry("capture", 1, tree="t2"), entry("capture_approved", 2, tree="t1", by="a")]
    assert evidence_summary(entries, "", "")["capture"] == {"tree": "t2", "approved": False}
