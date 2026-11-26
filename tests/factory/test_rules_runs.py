"""F11 run_breakdowns, expected values from the run table of fixture F1."""

from factory_values import FROM, RUNS, TO, nov, run

from code_factory.factory.models import KeyCount
from code_factory.factory.rules.runs import run_breakdowns


def counts(items: list[KeyCount]) -> list[tuple[str, int]]:
    return [(i.key, i.runs) for i in items]


def test_the_fixture_is_counted_five_ways_as_the_spec_works_it_out() -> None:
    got = run_breakdowns(RUNS, FROM, TO)
    assert got.total == 13
    assert counts(got.by_stage) == [
        ("build", 6),
        ("review", 4),
        ("eval", 1),
        ("judge", 1),
        ("spec", 1),
    ]
    assert counts(got.by_state) == [("finished", 9), ("failed", 2), ("running", 1), ("stopped", 1)]
    assert counts(got.by_source) == [("board", 11), ("eval", 1), ("judge", 1)]
    assert counts(got.by_model) == [("opus", 8), ("sonnet", 5)]
    assert counts(got.by_agent) == [("builder", 8), ("reviewer", 4), ("judge", 1)]


def test_a_run_started_exactly_at_from_counts_and_exactly_at_to_does_not() -> None:
    at_from = run("a", None, "build", "b", "m", "finished", FROM)
    at_to = run("b", None, "build", "b", "m", "finished", TO)
    before = run("c", None, "build", "b", "m", "finished", FROM - 1)
    assert run_breakdowns([at_from, at_to, before], FROM, TO).total == 1


def test_an_empty_model_or_agent_reads_default() -> None:
    plain = run("a", None, "build", "", "", "finished", nov(2))
    got = run_breakdowns([plain], FROM, TO)
    assert (counts(got.by_model), counts(got.by_agent)) == ([("default", 1)], [("default", 1)])


def test_equal_counts_are_ordered_by_key() -> None:
    runs = [run(k, None, k, "b", "m", "finished", nov(2)) for k in ("zeta", "alpha", "mid")]
    assert counts(run_breakdowns(runs, FROM, TO).by_stage) == [
        ("alpha", 1),
        ("mid", 1),
        ("zeta", 1),
    ]


def test_no_runs_gives_empty_lists() -> None:
    got = run_breakdowns([], FROM, TO)
    assert (got.total, got.by_stage, got.by_model) == (0, [], [])
