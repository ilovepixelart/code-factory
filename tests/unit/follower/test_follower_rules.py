"""The follower's pure rules against the previous implementation's goldens and hand cases."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from code_factory.follower.models import ActiveRunFact, Card
from code_factory.follower.rules import (
    FAILURES_CAP,
    due_for_fix,
    due_for_review,
    failure_streak,
    period,
    plan_queue,
    recurring_due,
    retry_wait,
    transient,
)

GOLDEN = json.loads(
    (Path(__file__).parents[2] / "support/golden/formats/follower/cases.json").read_text()
)


def _case(case: dict[str, Any]) -> tuple[list[Card], list[ActiveRunFact], dict[str, int]]:
    names = {c["repository_path"]: c["repository"] for c in case["cards"]}
    names |= {"/r/other": "other", "/r/sample": "sample"}
    cards = [
        Card.model_validate({k: v for k, v in c.items() if k != "repository_path"})
        for c in case["cards"]
    ]
    runs = [
        ActiveRunFact(repository=names[r["repository"]], ticket_id=r["ticket_id"],
                      stage=r["stage"], active=r["active"])
        for r in case["runs"]
    ]  # fmt: skip
    slots: dict[str, int] = {str(names[path]): int(n) for path, n in case["slots"].items()}
    return cards, runs, slots


@pytest.mark.parametrize(
    ("case", "expected"),
    list(zip(GOLDEN["queues"]["cases"], GOLDEN["queues"]["expected"].values(), strict=True)),
    ids=[c["name"] for c in GOLDEN["queues"]["cases"]],
)
def test_the_queue_plans_as_the_golden(
    case: dict[str, Any], expected: list[dict[str, Any]]
) -> None:
    cards, runs, slots = _case(case)
    plan = plan_queue(cards, runs, slots=slots, overall=case["overall"], limits=case["limits"])
    assert [p.model_dump() for p in plan] == expected


def test_a_column_limit_holds_after_the_caps_above_it() -> None:
    cards = [Card(id=f"CF-{n}", repository="r", stage="build") for n in (1, 2)]
    plan = plan_queue(cards, [], slots={"r": 5}, overall=None, limits={"build": 1})
    assert [p.reason for p in plan] == ["", "Build 1 of 1"]


def test_the_teams_rule_has_the_last_word() -> None:
    cards = [Card(id="CF-1", repository="r", stage="spec")]
    plan = plan_queue(
        cards, [], slots={"r": 1}, overall=None, limits={}, rule=lambda _card: "no agent takes spec"
    )
    assert plan[0].reason == "no agent takes spec"


NOW = datetime(2026, 9, 21, 10, tzinfo=UTC)


def _failed(failures: int, ended_s_ago: float, **fields: object) -> Card:
    ended = NOW - timedelta(seconds=ended_s_ago)
    return Card.model_validate(
        {"id": "CF-1", "repository": "r", "stage": "build", "failures": failures,
         "last_end": ended, **fields}
    )  # fmt: skip


def _note(card: Card) -> str:
    return plan_queue([card], [], slots={"r": 1}, overall=None, limits={}, now=NOW)[0].reason


def test_a_failed_run_waits_ten_seconds_before_it_is_tried_again() -> None:
    assert _note(_failed(1, 9)) == "tried again at 10:00:01 UTC, after 1 failed run"
    assert _note(_failed(1, 10)) == ""


def test_the_wait_doubles_with_each_failure_in_a_row() -> None:
    assert _note(_failed(3, 39)) == "tried again at 10:00:01 UTC, after 3 failed runs"
    assert _note(_failed(3, 40)) == ""


def test_a_ticket_whose_runs_failed_up_to_the_cap_waits_for_the_owner() -> None:
    waits = _note(_failed(FAILURES_CAP, 3600))

    assert waits == (
        f"not started: its last {FAILURES_CAP} runs failed; "
        "start it by hand once the cause is fixed"
    )
    assert _note(_failed(FAILURES_CAP - 1, 3600)) == ""


def test_a_usage_limit_holds_the_ticket_until_it_lifts() -> None:
    until = NOW + timedelta(minutes=30)

    assert _note(_failed(0, 5, limited_until=until)) == "a usage limit holds it until 10:30 UTC"
    assert _note(_failed(0, 5, limited_until=NOW)) == ""


def test_a_waiting_ticket_leaves_its_slot_to_the_next_one() -> None:
    cards = [_failed(2, 1), Card(id="CF-2", repository="r", stage="build")]

    plan = plan_queue(cards, [], slots={"r": 1}, overall=None, limits={}, now=NOW)

    assert [(p.id, p.reason) for p in plan] == [
        ("CF-1", "tried again at 10:00:19 UTC, after 2 failed runs"),
        ("CF-2", ""),
    ]


def test_a_ticket_in_review_is_due_a_review_once_per_build() -> None:
    assert due_for_review("review", review_on=True, last_stage=None)
    assert due_for_review("review", review_on=True, last_stage="build")
    assert not due_for_review("review", review_on=True, last_stage="review")
    assert not due_for_review("review", review_on=False, last_stage="build")
    assert not due_for_review("build", review_on=True, last_stage="build")


def test_a_ticket_a_review_returned_is_due_a_fix_until_a_build_run_commits() -> None:
    returned = NOW - timedelta(minutes=5)
    before = (NOW - timedelta(minutes=9), True)
    after_empty = (NOW - timedelta(minutes=1), False)
    after_commits = (NOW - timedelta(minutes=1), True)

    assert due_for_fix("build", returned, [])
    assert due_for_fix("build", returned, [before, after_empty])
    assert not due_for_fix("build", returned, [after_commits])
    assert not due_for_fix("build", None, [])
    assert not due_for_fix("review", returned, [])


def test_a_card_due_a_fix_or_a_review_is_planned() -> None:
    cards = [
        Card(id="CF-1", repository="r", stage="build", work_done=True, fix_due=True),
        Card(id="CF-2", repository="r", stage="review", work_done=True, review_due=True),
        Card(id="CF-3", repository="r", stage="build", work_done=True),
    ]

    plan = plan_queue(cards, [], slots={"r": 5}, overall=None, limits={})

    assert sorted(p.id for p in plan) == ["CF-1", "CF-2"]


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        ([], 0),
        (["finished", "failed"], 0),
        (["failed", "failed", "finished", "failed"], 2),
        (["running", "failed", "stopped", "failed"], 1),
        (["limited", "failed"], 0),
    ],
)
def test_the_streak_counts_the_newest_failed_runs_in_a_row(
    states: list[str], expected: int
) -> None:
    assert failure_streak(states) == expected


@pytest.mark.parametrize(
    ("case", "expected"),
    list(zip(GOLDEN["periods"]["cases"], GOLDEN["periods"]["expected"], strict=True)),
)
def test_periods_as_the_golden(case: dict[str, Any], expected: str) -> None:
    assert period(case["every"], datetime.fromtimestamp(case["at"], UTC)) == expected


@pytest.mark.parametrize(
    ("log", "expected"),
    list(zip(GOLDEN["transient"]["cases"], GOLDEN["transient"]["expected"], strict=True)),
)
def test_transient_failures_as_the_golden(log: str, expected: bool) -> None:
    assert transient(log) is expected


@pytest.mark.parametrize(
    ("attempt", "seconds"), [(1, 10), (2, 20), (3, 40), (4, 80), (5, 160), (6, 300), (7, 300)]
)
def test_retry_waits_double_up_to_five_minutes(attempt: int, seconds: int) -> None:
    assert retry_wait(attempt) == timedelta(seconds=seconds)


def test_a_recurring_entry_files_once_per_period() -> None:
    now = datetime(2026, 9, 21, 10, tzinfo=UTC)
    entries = [
        {"title": "Rotate keys", "every": "month", "type": "upgrade", "labels": "ops, security"},
        {"title": "", "every": "day"},
        {"title": "Odd", "every": "year"},
    ]

    [due] = recurring_due(entries, set(), now)

    assert due == {
        "title": "Rotate keys", "type": "upgrade", "source": "recurring:Rotate keys@2026-09",
        "labels": ["ops", "security"],
    }  # fmt: skip
    assert recurring_due(entries, {"recurring:Rotate keys@2026-09"}, now) == []


def test_an_exhausted_repair_keeps_its_note_without_holding_a_queue_slot() -> None:
    exhausted = Card(
        id="CF-1", repository="r", stage="build", fix_due=True, repair_hold="Fix rounds exhausted"
    )
    ordinary = Card(id="CF-2", repository="r", stage="build")

    plan = plan_queue([exhausted, ordinary], [], slots={"r": 1}, overall=None, limits={})

    assert [(card.id, card.reason) for card in plan] == [
        ("CF-1", "Fix rounds exhausted"),
        ("CF-2", ""),
    ]
