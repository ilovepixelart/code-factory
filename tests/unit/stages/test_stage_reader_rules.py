"""Readers over a ticket's activity: the run that started after a record, the owner's answers that
wait, the screens that wait. Expected values: the previous implementation's screens test (two
asserts) and hand cases for each branch."""

from datetime import UTC, datetime

from code_factory.stages.models import Record
from code_factory.stages.rules import (
    answered_before,
    answers_waiting,
    sent_back,
    started_after,
    waiting_capture,
)


def at(minute: int, second: int = 0) -> datetime:
    return datetime(2026, 10, 4, 10, minute, second, tzinfo=UTC)


def rec(kind: str, minute: int = 0, **data: object) -> Record:
    return Record(kind=kind, at=at(minute), data=data)


def test_a_capture_waits_only_while_neither_approved_nor_sent_back() -> None:
    captured = rec("capture", tree="t1")
    approved = rec("capture_approved", 1, tree="t1")
    back = rec("capture_changes", 1, tree="t1", reason="Too dark")

    assert waiting_capture([captured], "t1") == captured
    assert waiting_capture([captured], "t2") is None
    assert waiting_capture([captured, approved], "t1") is None
    assert waiting_capture([captured, back], "t1") is None


def test_a_capture_of_the_tree_waits_though_another_tree_was_approved() -> None:
    history = [rec("capture", tree="t1"), rec("capture_approved", 1, tree="t0")]

    assert waiting_capture(history, "t1") is not None


def test_the_latest_time_the_screens_of_a_tree_were_sent_back() -> None:
    first, second = rec("capture_changes", 1, tree="t1"), rec("capture_changes", 2, tree="t1")

    assert sent_back([first, second, rec("capture_changes", 3, tree="t2")], "t1") == second
    assert sent_back([], "t1") is None


def test_a_run_is_the_first_after_a_record_when_nothing_started_between() -> None:
    history = [rec("answer", 1), rec("run.started", 2, run="r1"), rec("run.started", 3, run="r2")]

    assert started_after(history, "r1", "answer")
    assert not started_after(history, "r2", "answer")
    assert not started_after(history, "r9", "answer")


def test_an_answer_waits_until_a_run_that_started_after_it_applied_them() -> None:
    answer = rec("answer", 1, apply=True)
    noted = rec("answer", 1, apply=False)
    applied_before = rec("answers_applied", 2, started=at(0).timestamp())
    applied_after = rec("answers_applied", 2, started=at(5).timestamp())

    assert answers_waiting([answer, noted]) == [answer]
    assert answers_waiting([answer, applied_before]) == [answer]
    assert answers_waiting([answer, applied_after]) == []


def test_an_answer_is_before_a_run_only_in_an_earlier_second() -> None:
    answer = Record(kind="answer", at=datetime(2026, 10, 4, 10, 1, 5, 900_000, tzinfo=UTC), data={})
    second = datetime(2026, 10, 4, 10, 1, 5, tzinfo=UTC).timestamp()

    assert answered_before(answer, second + 1)
    assert not answered_before(answer, second)
    assert not answered_before(answer, second + 0.5)
