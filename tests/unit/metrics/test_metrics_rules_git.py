"""Merges, branch names, remotes, reverts, autonomy and check verdicts, from hand-worked logs."""

from datetime import UTC, datetime

import pytest

from code_factory.metrics.models import Autonomy, CheckRecord, ChecksVerdict, Merge
from code_factory.metrics.rules.merges import (
    autonomy_class,
    checks_verdict,
    github_web,
    parse_merges,
    ticket_of,
)
from code_factory.metrics.rules.reverts import reverted_commits
from git_log_values import REVERTS, SHIPPED, record


def merge(
    commit_head: tuple[str, str],
    pull: int | None,
    branch: str,
    ticket: str | None,
    times: tuple[int, int],
) -> Merge:
    commit, head = commit_head
    return Merge(
        commit=commit,
        head=head,
        pull=pull,
        branch=branch,
        ticket=ticket,
        at=times[0],
        started=times[1],
    )


def test_merges_name_their_ticket_and_when_the_work_started() -> None:
    assert parse_merges(SHIPPED, 0.0) == [
        merge(("m3", "b3"), 9, "process/clean-slate", None, (1800, 1300)),
        merge(("m1", "a2"), 7, "ticket/cf-12", "CF-12", (1500, 1100)),
    ]


def test_merges_before_the_window_are_left_out() -> None:
    assert parse_merges(SHIPPED, 1600.0) == [
        merge(("m3", "b3"), 9, "process/clean-slate", None, (1800, 1300))
    ]


def test_a_merge_exactly_at_the_window_start_is_kept() -> None:
    assert [m.commit for m in parse_merges(SHIPPED, 1500.0)] == ["m3", "m1"]


def test_a_log_with_no_merge_ships_nothing() -> None:
    assert parse_merges(record("c0", "", 1000, "Start"), 0.0) == []
    assert parse_merges("", 0.0) == []


def test_a_merge_subject_without_a_number_has_no_pull() -> None:
    log = (
        record("m1", "c0 a1", 1500, "Merge pull request #x from o/ticket/cf-1")
        + record("a1", "c0", 1100, "work")
        + record("c0", "", 1000, "Start")
    )
    assert [(m.pull, m.ticket) for m in parse_merges(log, 0.0)] == [(None, "CF-1")]


def test_a_merge_that_is_not_the_github_form_is_not_a_pull_request() -> None:
    log = (
        record("m1", "c0 a1", 1500, "Merge branch 'x' into main")
        + record("a1", "c0", 1100, "work")
        + record("c0", "", 1000, "Start")
    )
    assert parse_merges(log, 0.0) == []


def test_only_the_first_parent_line_counts() -> None:
    # m9 is reachable only through the second parent of m1: not a merge into main.
    log = "".join(
        [
            record("m1", "c0 m9", 1500, "Merge pull request #7 from o/ticket/cf-12"),
            record("m9", "c0 x1", 1400, "Merge pull request #5 from o/ticket/cf-5"),
            record("x1", "c0", 1300, "work"),
            record("c0", "", 1000, "Start"),
        ]
    )
    assert [m.commit for m in parse_merges(log, 0.0)] == ["m1"]


@pytest.mark.parametrize(
    ("branch", "expected"),
    [
        ("ticket/cf-12", "CF-12"),
        ("cf-12-code", "CF-12"),
        ("feat/CF-1", "CF-1"),
        ("process/clean-slate", None),
        ("x-", None),
        ("", None),
        ("a1-5", None),
    ],
)
def test_a_branch_names_a_ticket_in_its_last_part(branch: str, expected: str | None) -> None:
    assert ticket_of(branch) == expected


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("git@github.com:o/r.git", "https://github.com/o/r"),
        ("https://github.com/o/r", "https://github.com/o/r"),
        ("https://github.com/o/r.git\n", "https://github.com/o/r"),
        ("ssh://git@github.com/o/r.git", "https://github.com/o/r"),
        ("https://gitlab.com/o/r.git", None),
        ("https://github.com/", None),
        ("", None),
    ],
)
def test_the_web_address_comes_from_a_github_remote_only(remote: str, expected: str | None) -> None:
    assert github_web(remote) == expected


def test_a_commit_naming_a_merged_pull_request_reverts_its_merge() -> None:
    assert reverted_commits(REVERTS) == {"m1", "m2"}


def test_a_log_with_no_revert_or_no_log_reverts_nothing() -> None:
    log = "".join(
        [
            record("m1", "c0 a1", 1100, "Merge pull request #7 from o/ticket/cf-12"),
            record("a1", "c0", 1050, "CF-12: work"),
            record("c0", "", 1000, "Start"),
        ]
    )
    assert reverted_commits(log) == set()
    assert reverted_commits("") == set()


MERGE = "bbbbbbb1"  # merges pull request #7, which brings in WORK
WORK = "aaaaaaa1"


def revert_log(message: str) -> str:
    """MERGE merges WORK; a later merge brings r1, whose message is `message`."""
    return "".join(
        [
            record("m2", f"{MERGE} r1", 1300, "Merge pull request #8 from o/revert"),
            record("r1", MERGE, 1250, message),
            record(MERGE, f"c0 {WORK}", 1100, "Merge pull request #7 from o/ticket/cf-12"),
            record(WORK, "c0", 1050, "CF-12: work"),
            record("c0", "", 1000, "Start"),
        ]
    )


@pytest.mark.parametrize(
    "message",
    [
        f"Undo\n\nThis reverts commit {WORK}.",
        f"Revert merge {MERGE}",
        "Undo\n\nReverts #7",
        "Undo\n\nreverts o/sample#7",
    ],
)
def test_each_phrasing_of_a_revert_names_the_merge(message: str) -> None:
    assert reverted_commits(revert_log(message)) == {MERGE}


def test_a_short_commit_id_is_not_a_revert_reference() -> None:
    assert reverted_commits(revert_log(f"Undo\n\nThis reverts commit {WORK[:6]}.")) == set()


def test_an_id_prefix_matching_two_commits_is_ignored() -> None:
    log = "".join(
        [
            record("m2", f"{MERGE} r1", 1300, "Merge pull request #8 from o/revert"),
            record("r1", MERGE, 1250, "Undo\n\nThis reverts commit abcdef0."),
            record(MERGE, "c0 abcdef02", 1100, "Merge pull request #7 from o/ticket/cf-12"),
            record("abcdef02", "abcdef01", 1040, "two"),
            record("abcdef01", "c0", 1030, "one"),
            record("c0", "", 1000, "Start"),
        ]
    )
    assert reverted_commits(log) == set()


@pytest.mark.parametrize(
    ("rev_list", "made", "recorded", "expected"),
    [
        # A, H, B are all made by runs.
        ("B A\nH A\nA\n", {"A", "H", "B"}, True, Autonomy.AUTONOMOUS),
        # A hand commit H between two runs.
        ("B H\nH A\nA\n", {"A", "B"}, True, Autonomy.ASSISTED),
        # Main merged into the branch: a merge commit none of whose later parents is in range.
        ("M B X\nB A\nA\n", {"A", "B"}, True, Autonomy.AUTONOMOUS),
        # The merge of main is skipped, but a commit not made by a run still counts.
        ("M B X\nB A\nA\n", {"A"}, True, Autonomy.ASSISTED),
        # A squash or rebase: git could not read the range.
        (None, {"A"}, True, Autonomy.UNKNOWN),
        # No run recorded its commits.
        ("B A\nA\n", set(), False, Autonomy.UNKNOWN),
    ],
)
def test_autonomy_is_judged_on_the_commits_the_merge_brought_in(
    rev_list: str | None, made: set[str], recorded: bool, expected: Autonomy
) -> None:
    assert autonomy_class(rev_list, made, recorded=recorded) == expected


def test_a_merge_commit_that_brought_in_a_commit_of_the_range_counts() -> None:
    # M merges the branch's own side line S into B: its later parent S is in the range.
    rev_list = "M B S\nB A\nS A\nA\n"
    assert autonomy_class(rev_list, {"A", "B", "S"}, recorded=True) == Autonomy.ASSISTED


def at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


def test_the_last_record_naming_the_head_decides_the_verdict() -> None:
    records = [
        CheckRecord(ticket_id="CF-1", commit="aaa", exit_code=0, at=at(1)),
        CheckRecord(ticket_id="CF-1", commit="bbb", exit_code=1, at=at(2)),
        CheckRecord(ticket_id="CF-1", commit="bbb", exit_code=0, at=at(3)),
        CheckRecord(ticket_id="CF-1", commit="ccc", exit_code=0, at=at(4)),
        CheckRecord(ticket_id="CF-1", commit="ccc", exit_code=137, at=at(5)),
        CheckRecord(ticket_id="CF-1", commit="eee", exit_code=None, at=at(7)),
    ]
    heads = ["aaa", "bbb", "ccc", "ddd", "eee", "fff", ""]
    assert [checks_verdict(records, h) for h in heads] == [
        ChecksVerdict.PASSED,
        ChecksVerdict.PASSED,
        ChecksVerdict.FAILED,
        ChecksVerdict.NONE,
        ChecksVerdict.FAILED,
        ChecksVerdict.NONE,
        ChecksVerdict.NONE,
    ]


def test_records_are_ordered_by_time_not_by_position() -> None:
    records = [
        CheckRecord(ticket_id="CF-1", commit="aaa", exit_code=0, at=at(9)),
        CheckRecord(ticket_id="CF-1", commit="aaa", exit_code=1, at=at(2)),
    ]
    assert checks_verdict(records, "aaa") == ChecksVerdict.PASSED


def test_a_change_landed_before_a_pull_request_does_not_revert_it() -> None:
    log = "".join(
        [
            record("m2", "m1 w2", 1700, "Merge pull request #7 from o/ticket/cf-12"),
            record("w2", "c0", 1650, "CF-12: work"),
            record("m1", "c0 w1", 1500, "Merge pull request #3 from o/ticket/cf-3"),
            record("w1", "c0", 1450, "Plans\n\nReverts #7 once it lands"),
            record("c0", "", 1000, "Start"),
        ]
    )
    assert reverted_commits(log) == set()
