"""Boundaries of the pure rules: ties, caps, instants and the flags an agent row carries."""

from datetime import UTC, datetime

from test_metrics_rules_flow import NOW, merge, page
from test_metrics_rules_reports import START, run, timeline

from code_factory.metrics.models import CheckRecord, ChecksVerdict, ColumnTime
from code_factory.metrics.rules.agents import agent_rows
from code_factory.metrics.rules.columns import column_times
from code_factory.metrics.rules.merges import WALK_LIMIT, checks_verdict, parse_merges
from git_log_values import record


def test_an_agent_row_is_estimated_only_when_a_cost_it_counts_is_estimated() -> None:
    unpriced = run(1.0, estimated=True)
    [only] = agent_rows([unpriced], 0.0)
    assert (only.cost, only.estimated) == (None, None)
    [mixed] = agent_rows([unpriced, run(2.0, cost=1.0, estimated=True)], 0.0)
    assert (mixed.cost, mixed.estimated) == (1.0, True)


def test_a_ticket_created_in_the_window_that_never_moved_is_listed_with_its_filing() -> None:
    rows = column_times([("CF-2", timeline([(0.0, "spec")]))], START, START + 600.0)
    assert rows == [ColumnTime(ticket="CF-2", minutes=(10, None, None), now="spec")]


def test_a_build_that_started_at_the_instant_of_the_merge_still_completes() -> None:
    merges = [merge(1, NOW - 100, ticket_id="CF-1")]
    at_merge = page(merges, build_starts={"sample": {"CF-1": NOW - 100}})
    after_merge = page(merges, build_starts={"sample": {"CF-1": NOW - 99}})
    assert (at_merge.completion.merged, after_merge.completion.merged) == (1, 0)


def test_two_records_of_one_instant_are_decided_by_the_later_one_in_the_list() -> None:
    at = datetime.fromtimestamp(5, UTC)
    failed = CheckRecord(ticket_id="CF-1", commit="aaa", exit_code=1, at=at)
    passed = CheckRecord(ticket_id="CF-1", commit="aaa", exit_code=0, at=at)
    assert checks_verdict([failed, passed], "aaa") == ChecksVerdict.PASSED
    assert checks_verdict([passed, failed], "aaa") == ChecksVerdict.FAILED


def test_the_walk_to_a_branchs_first_commit_stops_after_the_cap() -> None:
    length = WALK_LIMIT + 50
    chain = [
        record(f"w{n}", f"w{n + 1}" if n < length - 1 else "c0", 2_000_000 - n, "work")
        for n in range(length)
    ]
    log = record("m1", "c0 w0", 3_000_000, "Merge pull request #1 from o/ticket/cf-1")
    log += "".join(chain) + record("c0", "", 1000, "Start")
    [only] = parse_merges(log, 0.0)
    # w0 is the newest commit read first; the walk reads WALK_LIMIT of them, the oldest is w9999.
    assert only.started == 2_000_000 - (WALK_LIMIT - 1)
