"""Column minutes, gate step tables and agent rows, from hand-worked timelines and runs."""

from datetime import UTC, datetime

import pytest

from code_factory.metrics.models import ColumnTime, RunFacts, StepRun, Transition
from code_factory.metrics.rules.agents import agent_rows, ending_words
from code_factory.metrics.rules.columns import column_medians, column_times, minutes
from code_factory.metrics.rules.gates import (
    columns_table,
    revert_line,
    steps_table,
    summarize_steps,
)

START = 1_793_000_000.0
MINUTE = 60.0
HEADER = "step         runs  median  slowest  passed  failed  flaky  waited  slowest on\n"


def timeline(moves: list[tuple[float, str]]) -> list[Transition]:
    return [Transition(at=START + at, stage=stage) for at, stage in moves]


def row(ticket: str, spent: tuple[int | None, int | None, int | None], now: str) -> ColumnTime:
    return ColumnTime(ticket=ticket, minutes=spent, now=now)


def test_column_minutes_count_the_current_column_up_to_now() -> None:
    tickets = [("CF-1", timeline([(0.0, "spec"), (20 * MINUTE, "build")]))]
    assert column_times(tickets, START, START + 50 * MINUTE) == [
        row("CF-1", (20, 30, None), "build")
    ]


def test_column_minutes_round_half_up_to_the_nearest_minute() -> None:
    moves = [(0.0, "spec"), (89.0, "build"), (179.0, "review"), (209.0, "merged")]
    rows = column_times([("CF-1", timeline(moves))], START, START + 999 * MINUTE)
    assert rows == [row("CF-1", (1, 2, 1), "merged")]


@pytest.mark.parametrize(("seconds", "expected"), [(29, 0), (30, 1), (89, 1), (90, 2), (0, 0)])
def test_minutes_are_whole_and_half_rounds_up(seconds: float, expected: int) -> None:
    assert minutes(seconds) == expected


def test_a_ticket_that_did_not_move_since_the_window_start_is_left_out() -> None:
    tickets = [
        ("CF-1", timeline([(0.0, "spec"), (10 * MINUTE, "build")])),
        ("CF-2", timeline([(0.0, "spec"), (59 * MINUTE + 59, "build")])),
        ("CF-3", timeline([(0.0, "spec"), (60 * MINUTE, "build")])),
        ("CF-4", timeline([(0.0, "spec"), (70 * MINUTE, "build")])),
    ]
    rows = column_times(tickets, START + 60 * MINUTE, START + 100 * MINUTE)
    assert rows == [row("CF-4", (70, 30, None), "build"), row("CF-3", (60, 40, None), "build")]


def test_tickets_that_moved_at_the_same_instant_are_ordered_by_id() -> None:
    moves = [(0.0, "spec"), (60.0, "build")]
    tickets = [("CF-9", timeline(moves)), ("CF-2", timeline(moves))]
    assert [r.ticket for r in column_times(tickets, START, START + 600)] == ["CF-2", "CF-9"]


def test_the_median_of_a_column_skips_tickets_that_never_entered_it() -> None:
    rows = [
        row("CF-1", (10, 5, None), "merged"),
        row("CF-2", (30, 15, None), "merged"),
        row("CF-3", (20, None, None), "merged"),
    ]
    assert column_medians(rows) == (20.0, 5.0, None)


def step_run(
    ticket: str, at: str, seconds: dict[str, int] | None = None, **extra: object
) -> StepRun:
    fields: dict[str, object] = {
        "ticket_id": ticket,
        "at": datetime.fromisoformat(at),
        "seconds": seconds or {},
        "states": {},
        "retried": [],
        "lock_waits": {},
        "slept": False,
    }
    fields.update(extra)
    return StepRun.model_validate(fields)


def three_runs() -> list[StepRun]:
    return [
        step_run("CF-1", "2026-11-01T10:00:00+00:00", {"rust-test": 30, "web-build": 2}),
        step_run("CF-2", "2026-11-01T09:00:00+00:00"),
        step_run("CF-2", "2026-11-01T11:00:00+00:00", {"rust-test": 50}),
        step_run("CF-3", "2026-11-01T12:00:00+00:00", {"rust-test": 90, "web-build": 1}),
        step_run("CF-4", "2026-11-01T13:00:00+00:00", {"rust-test": 999}, slept=True),
    ]


def test_each_step_has_its_median_slowest_and_ticket_over_the_runs_with_seconds() -> None:
    table = steps_table(summarize_steps(three_runs(), 50))
    assert table == (
        f"{HEADER}"
        "rust-test       3      50       90    100%      0%     0%       0  CF-3\n"
        "web-build       2       1        2    100%      0%     0%       0  CF-1\n"
    )


def test_last_reads_only_the_newest_runs_that_carry_step_data() -> None:
    table = steps_table(summarize_steps(three_runs(), 2))
    assert table == (
        f"{HEADER}"
        "rust-test       2      50       90    100%      0%     0%       0  CF-3\n"
        "web-build       1       1        1    100%      0%     0%       0  CF-3\n"
    )


def test_an_older_slower_run_and_a_step_only_it_reported_are_left_out_of_the_newest() -> None:
    runs = [
        step_run("CF-1", "2026-11-01T10:00:00+00:00", {"rust-test": 200, "web-e2e": 120}),
        step_run("CF-1", "2026-11-01T12:00:00+00:00", {"rust-test": 20}),
        step_run("CF-2", "2026-11-01T11:00:00+00:00", {"rust-test": 10}),
    ]
    table = steps_table(summarize_steps(runs, 2))
    assert (
        table
        == f"{HEADER}rust-test       2      10       20    100%      0%     0%       0  CF-1\n"
    )


def test_no_run_with_step_data_is_no_step() -> None:
    assert summarize_steps([step_run("CF-1", "2026-11-01T10:00:00+00:00")], 50) == []


def test_a_failed_a_flaky_and_a_waiting_step_are_counted_and_one_with_no_pass_prints_dashes() -> (
    None
):
    runs = [
        step_run(
            "CF-1",
            "2026-11-01T10:00:00+00:00",
            {"lint": 5},
            states={"lint": "passed", "e2e": "failed", "deps": "started"},
            retried=["lint"],
            lock_waits={"lint": 7, "e2e": 3},
        ),
        step_run(
            "CF-2",
            "2026-11-01T11:00:00+00:00",
            {"lint": 9},
            states={"lint": "failed"},
            lock_waits={"lint": 2},
        ),
    ]
    steps = summarize_steps(runs, 50)
    assert [(s.step, s.runs, s.passed, s.failed, s.flaky, s.waited) for s in steps] == [
        ("lint", 2, 1, 1, 1, 9),
        ("e2e", 1, 0, 1, 0, 3),
    ]
    assert steps_table(steps) == (
        "step    runs  median  slowest  passed  failed  flaky  waited  slowest on\n"
        "lint       2       5        9     50%     50%    50%       9  CF-2\n"
        "e2e        1       -        -      0%    100%     0%       3  -\n"
    )


def test_steps_with_an_equal_median_are_ordered_by_name() -> None:
    runs = [step_run("CF-1", "2026-11-01T10:00:00+00:00", {"b": 5, "a": 5, "c": 6})]
    assert [s.step for s in summarize_steps(runs, 50)] == ["c", "a", "b"]


def test_the_newest_ticket_names_a_tie_for_slowest() -> None:
    runs = [
        step_run("CF-1", "2026-11-01T10:00:00+00:00", {"x": 9}),
        step_run("CF-2", "2026-11-01T11:00:00+00:00", {"x": 9}),
    ]
    assert summarize_steps(runs, 50)[0].slowest_on == "CF-2"


def test_the_step_column_is_at_least_eight_wide() -> None:
    table = steps_table(
        summarize_steps([step_run("CF-1", "2026-11-01T10:00:00+00:00", {"a": 1})], 5)
    )
    assert table.splitlines()[0].startswith("step    runs")


def test_the_columns_section_prints_a_title_a_header_and_a_line_per_ticket() -> None:
    rows = [row("CF-1", (20, 30, None), "build"), row("CF-12345678", (None, 1, 2), "merged")]
    assert columns_table(rows, "2026-11-01T10:00:00Z") == (
        "minutes in each column of the tickets that moved since 2026-11-01T10:00:00Z\n"
        "ticket            spec  build review  now\n"
        "CF-1                20     30      -  build\n"
        "CF-12345678          -      1      2  merged\n"
    )


def test_the_revert_line_gives_the_share_as_a_whole_percent() -> None:
    assert revert_line(8, 1, "2026-11-01T10:00:00Z") == (
        "merges since 2026-11-01T10:00:00Z: 8, reverted later: 1 (13%)\n"
    )


def run(  # noqa: PLR0913  # a fixture builder
    started: float,
    *,
    agent: str = "",
    model: str = "opus",
    connection: str = "",
    exit_code: int | None = 0,
    halted: str = "",
    tokens: int | None = None,
    cost: float | None = None,
    estimated: bool = False,
) -> RunFacts:
    return RunFacts(
        repository="sample",
        ticket_id="CF-1",
        stage="build",
        agent=agent,
        model=model,
        connection=connection,
        started_at=datetime.fromtimestamp(started, UTC),
        exit_code=exit_code,
        halted=halted,
        tokens=tokens,
        cost=cost,
        cost_estimated=estimated,
        commits=None,
    )


@pytest.mark.parametrize(
    ("halted", "exit_code", "expected"),
    [
        ("", -15, "stopped, no reason recorded"),
        ("", 2, "exit 2"),
        ("stopped at its cap: 5000 tokens", -15, "token cap"),
        ("stopped at its cap: 40 minutes", -15, "time cap"),
        (
            "read enough: stopped at 12 calls with no change in its worktree",
            1,
            "no change after 12 tool calls",
        ),
        ("read enough: stopped at 9 calls repeating one", 1, "one call repeated"),
        ("no progress in 3 iterations", 1, "no progress in 3 iterations"),
        ("lost: the host went away: twice", 1, "lost"),
    ],
)
def test_a_run_that_did_not_finish_ends_in_one_of_five_words(
    halted: str, exit_code: int, expected: str
) -> None:
    assert ending_words(halted, exit_code) == expected


def test_a_run_at_exactly_the_window_start_counts_and_one_second_before_does_not() -> None:
    rows = agent_rows([run(100.0), run(99.0)], 100.0)
    assert [r.runs for r in rows] == [1]


def test_the_default_agent_is_named_and_a_run_with_no_cost_or_tokens_leaves_them_none() -> None:
    [only] = agent_rows([run(100.0, cost=0.2)], 0.0)
    assert (only.agent, only.model, only.connection) == ("the default agent", "opus", "")
    assert (only.runs, only.finished, only.tokens, only.cost, only.estimated) == (
        1,
        1,
        None,
        0.2,
        None,
    )
    assert only.endings == []


def test_a_zero_cost_is_reported_and_none_is_not() -> None:
    [zero] = agent_rows([run(1.0, cost=0.0, tokens=0)], 0.0)
    [none] = agent_rows([run(1.0)], 0.0)
    assert (zero.cost, zero.tokens) == (0.0, 0)
    assert (none.cost, none.tokens) == (None, None)


def test_runs_are_classified_as_running_finished_stopped_or_failed() -> None:
    runs = [
        run(1.0, exit_code=None),
        run(2.0, exit_code=0),
        run(3.0, exit_code=-15),
        run(4.0, exit_code=1, halted="no progress in 3 iterations"),
        run(5.0, exit_code=1),
        run(6.0, exit_code=1),
    ]
    [only] = agent_rows(runs, 0.0)
    assert (only.runs, only.running, only.finished, only.stopped, only.failed) == (6, 1, 1, 2, 2)
    assert [(e.reason, e.count) for e in only.endings] == [
        ("exit 1", 2),
        ("no progress in 3 iterations", 1),
        ("stopped, no reason recorded", 1),
    ]


def test_an_estimated_cost_marks_the_row_and_only_then() -> None:
    [plain] = agent_rows([run(1.0, cost=1.0)], 0.0)
    [flagged] = agent_rows([run(1.0, cost=1.0), run(2.0, cost=2.0, estimated=True)], 0.0)
    assert (plain.estimated, flagged.estimated, flagged.cost) == (None, True, 3.0)


def test_rows_are_ordered_by_runs_then_by_agent_model_and_connection() -> None:
    runs = [
        run(1.0, agent="b"),
        run(2.0, agent="a", model="sonnet"),
        run(3.0, agent="a", model="opus"),
        run(4.0, agent="c"),
        run(5.0, agent="c"),
    ]
    assert [(r.agent, r.model, r.runs) for r in agent_rows(runs, 0.0)] == [
        ("c", "opus", 2),
        ("a", "opus", 1),
        ("a", "sonnet", 1),
        ("b", "opus", 1),
    ]
