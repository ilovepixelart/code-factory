"""Scores, report lines, comparison and scorers: the previous golden and hand-worked tables."""

from datetime import UTC, datetime, timedelta

import pytest

from code_factory.evals.models import (
    Answer,
    AnswerRow,
    EvalRecord,
    Filed,
    Kind,
    Role,
    Scorer,
    Setup,
    TaskRun,
)
from code_factory.evals.rules import (
    asked_of,
    compare,
    counts,
    due,
    parse_answer,
    pass_rate,
    report_lines,
    scores,
)

AT = datetime(2026, 11, 1, tzinfo=UTC)


def _runs(passes: dict[str, list[bool]]) -> tuple[TaskRun, ...]:
    return tuple(
        TaskRun(task_id=t, run_no=i, role=Role.BUILD, passed=p)
        for t, ps in passes.items()
        for i, p in enumerate(ps, 1)
    )


def _record(setup: Setup, passes: dict[str, list[bool]], **fields: object) -> EvalRecord:
    at_1, at_all, at_some = scores(passes)
    values: dict[str, object] = {
        "repository": "r", "set_name": "smoke", "kind": Kind.BUILD, "recorded_at": AT,
        "setup": setup, "runs": 3, "pass_at_1": at_1, "pass_k": at_all, "pass_at_k": at_some,
        "task_runs": _runs(passes),
    }  # fmt: skip
    return EvalRecord.model_validate(values | fields)


def test_scores_of_the_hand_worked_three_tasks() -> None:
    at_1, at_all, at_some = scores({"a": [True, True, False], "b": [True] * 3, "c": [False] * 3})
    assert (round(at_1, 4), round(at_all, 4), round(at_some, 4)) == (0.5556, 0.3333, 0.6667)
    assert scores({}) == (0.0, 0.0, 0.0)


def test_the_report_lines_match_the_previous_golden() -> None:
    first = _record(
        Setup(runtime="claude -p {prompt}", model="opus", instructions="abc123def456"),
        {"t1": [True, True, False]},
        pass_at_k=None, cost=1.5,
    )  # fmt: skip
    second = _record(
        Setup(runtime="/usr/local/bin/opencode run {prompt}", instructions="000000000000"),
        {}, runs=1, pass_at_1=0.0, pass_k=0.0, pass_at_k=None, cost=0.0,
    )  # fmt: skip
    third = _record(Setup(), {}, runs=2, pass_at_1=1.0, pass_k=0.5, pass_at_k=None, cost=0.125)

    assert report_lines([first, second, third]) == [
        (
            "build: claude opus instructions abc123def456: 3 runs per task, pass@1 67%,"
            " pass@k 100%, pass^k 0%, $1.50"
        ),
        (
            "build: opencode default model instructions 000000000000: 1 runs per task,"
            " pass@1 0%, pass@k 0%, pass^k 0%, $0.00"
        ),
        (
            "build: ? default model instructions : 2 runs per task, pass@1 100%, pass@k 0%,"
            " pass^k 50%, $0.12"
        ),
    ]


def test_only_the_newest_record_of_a_named_agent_is_reported() -> None:
    old = _record(Setup(agent="a", runtime="claude"), {"t": [True]})
    new = _record(Setup(agent="a", runtime="claude", model="m"), {"t": [True]})
    assert report_lines([old, new]) == report_lines([new])


def test_a_candidate_that_drops_pass_at_1_loses() -> None:
    base = _record(Setup(runtime="claude", model="a"), {"t1": [True] * 3, "t2": [True] * 3})
    cand = _record(
        Setup(runtime="claude", model="b"), {"t1": [True, True, False], "t2": [True] * 3}
    )

    result = compare([base, cand])

    assert result.loses
    assert result.lines[-1] == "loses: pass@1 -17 points, pass^k -50 points"


def test_an_equal_pass_at_1_with_a_better_pass_k_does_not_lose() -> None:
    base = _record(Setup(model="a"), {"t1": [True, False], "t2": [True, False]})
    cand = _record(Setup(model="b"), {"t1": [True, True], "t2": [False, False]})

    result = compare([base, cand])

    assert not result.loses
    assert result.lines[-1] == "does not lose: pass@1 +0 points, pass^k +50 points"


def test_runs_of_one_setup_have_nothing_to_compare() -> None:
    one = _record(Setup(model="a"), {"t": [True]})
    assert compare([one, one]).lines == ("nothing to compare: runs of one setup only",)
    assert compare([]).lines == ("nothing to compare: no recorded run",)


def test_the_scorer_sample_draws_by_the_fnv_position() -> None:
    scorer = Scorer(name="ran-tests", question="q", sample=0.5)
    asked = [s for s in ["s1", "s2", "s3", "s4", "s5", "s6"] if asked_of(scorer, s, "build")]
    assert asked == ["s3", "s4", "s5", "s6"]


def test_sample_zero_asks_nobody_and_one_asks_all() -> None:
    sessions = [f"s{i}" for i in range(200)]
    assert not any(asked_of(Scorer(name="x", question="q", sample=0), s, "") for s in sessions)
    assert all(asked_of(Scorer(name="x", question="q", sample=1), s, "") for s in sessions)


def test_a_scorer_of_another_stage_is_not_asked() -> None:
    assert not asked_of(Scorer(name="x", question="q", stage="review"), "s1", "build")


@pytest.mark.parametrize(
    ("text", "answer"),
    [("Answer: Yes.", Answer.YES), ("Answer: no!", Answer.NO), ("Answer: maybe", Answer.UNCLEAR),
     ("nothing", Answer.UNCLEAR)],
)  # fmt: skip
def test_an_answer_is_read_from_its_first_word(text: str, answer: Answer) -> None:
    assert parse_answer(text)[0] is answer


def _answer(session: str, answer: Answer, days_ago: float, scorer: str = "s") -> AnswerRow:
    return AnswerRow(
        session_id=session, scorer=scorer, answer=answer, evidence="e",
        at=AT - timedelta(days=days_ago),
    )  # fmt: skip


def test_the_week_and_month_rates_of_the_hand_worked_case() -> None:
    rows = [
        _answer("a", Answer.YES, 1), _answer("b", Answer.YES, 2), _answer("c", Answer.YES, 3),
        _answer("d", Answer.NO, 4), _answer("e", Answer.UNCLEAR, 5), _answer("f", Answer.NO, 20),
    ]  # fmt: skip
    week = counts(rows, "s", AT - timedelta(days=7))
    month = counts(rows, "s", AT - timedelta(days=30))
    assert (week.yes, week.no, week.unclear, pass_rate(week)) == (3, 1, 1, 0.75)
    assert pass_rate(month) == 0.6


def test_a_scorer_files_at_its_threshold_once_until_the_ticket_is_closed() -> None:
    scorer = Scorer(name="s", question="Did it run the tests?", threshold=10)
    nine = [_answer(f"x{i}", Answer.NO, 1 - i / 100) for i in range(9)]
    ten = [*nine, _answer("x9", Answer.NO, 0.5)]

    assert due(scorer, nine, []) is None
    firing = due(scorer, ten, [])
    assert firing is not None
    assert firing.title == "Scorer s: 10 sessions answered no"
    assert (
        due(
            scorer,
            [*ten, _answer("y", Answer.NO, 0.1)],
            [Filed(source=firing.source, open=True, id="CF-9")],
        )
        is None
    )
    closed = [Filed(source=firing.source, open=False, id="CF-9")]
    assert due(scorer, ten, closed) is None


def test_a_session_answering_no_twice_counts_once() -> None:
    scorer = Scorer(name="s", question="q", threshold=2)
    assert due(scorer, [_answer("a", Answer.NO, 2), _answer("a", Answer.NO, 1)], []) is None
