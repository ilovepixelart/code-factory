"""Which diff merges without a review and what holds a merge for one. Expected values: the previous
implementation's review-hold tests (worked by hand from the rule) and one case per return branch of
the hold decision, with the timeout boundary on both sides."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from code_factory.stages.models import BlockingFinding, Hold
from code_factory.stages.rules import (
    change_hold,
    findings_note,
    numstat,
    path_matches,
    plain,
    review_hold_decision,
    review_outcome,
    small,
)

CONFIG = ".code-factory/config.toml"
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def test_a_numstat_record_reads_as_its_changed_lines_and_its_path() -> None:
    records = ["3\t2\tsrc/a.py", "-\t-\tdocs/shot.png", "0\t7\tsrc/gone.py"]

    assert numstat("".join(f"{record}\0" for record in records)) == [
        (5, "src/a.py"),
        (None, "docs/shot.png"),
        (7, "src/gone.py"),
    ]


def test_a_numstat_record_the_rule_cannot_read_has_no_size() -> None:
    assert numstat("1\t1\tdocs/a\tb.md\0what\0") == [(2, "docs/a\tb.md"), (None, "what")]


def test_a_diff_is_small_up_to_the_bound_and_not_past_it() -> None:
    assert small([(399, "src/a.py"), (1, "src/b.py")], 400, [])
    assert not small([(400, "src/a.py"), (1, "src/b.py")], 400, [])


def test_a_diff_with_a_binary_file_is_not_small() -> None:
    assert not small([(1, "src/a.py"), (None, "docs/shot.png")], 400, [])


def test_one_file_in_a_sensitive_path_makes_the_whole_diff_wait() -> None:
    changed = [(1, "docs/a.md"), (1, "scripts/ci/gate.sh")]

    assert not small(changed, 400, ["scripts/**"])
    assert small(changed, 400, ["crates/**/secrets.rs"])


def test_the_file_that_holds_the_rule_is_sensitive_whatever_the_repository_lists() -> None:
    assert not small([(1, CONFIG)], 400, [])
    assert small([(1, CONFIG + ".md")], 400, [])


def test_a_path_differing_only_by_case_from_a_guarded_one_is_not_small() -> None:
    assert not small([(1, ".code-factory/Config.toml")], 400, [])
    assert not small([(1, "Scripts/gate.sh")], 400, ["scripts/**"])
    assert not small([(1, "scripts/gate.sh")], 400, ["Scripts/**"])
    assert small([(1, "Scripts/gate.sh")], 400, ["docs/**"])


@pytest.mark.parametrize(
    ("path", "pattern", "matches"),
    [
        ("scripts/ci/gate.sh", "scripts/**", True),
        ("scripts", "scripts/**", True),
        ("crates/a/b/secrets.rs", "crates/**/secrets.rs", True),
        ("crates/secrets.rs", "crates/**/secrets.rs", True),
        ("src/a.py", "src/*.py", True),
        ("src/sub/a.py", "src/*.py", False),
        ("src/a.py", "src/?.py", True),
        ("src/ab.py", "src/?.py", False),
        ("src/a1.py", "src/a[0-9].py", True),
        ("docs/a.md", "scripts/**", False),
        ("docs/x/y/a.md", "docs/**", True),
        ("web/src/a.ts", "web/*/a.ts", True),
        ("web/src/x/a.ts", "web/*/a.ts", False),
        ("a.md", "**/*.md", True),
        ("x/y/a.md", "**/*.md", True),
        ("docsx/a.md", "docs/**", False),
        ("crates/a.rs", "docs/**", False),
    ],
)
def test_a_pattern_matches_whole_folders_with_double_star_and_one_name_with_the_rest(
    path: str, pattern: str, matches: bool
) -> None:
    assert path_matches(path, pattern) is matches


def raw(before: str, after: str, path: str) -> str:
    return f":{before} {after} 1111111 2222222 M\0{path}\0"


def test_changes_to_plain_files_are_plain() -> None:
    changes = [
        raw("100644", "100644", "src/a.py"),
        raw("000000", "100755", "scripts/new.sh"),
        raw("100644", "000000", "src/gone.py"),
    ]

    assert plain("".join(changes))
    assert plain("")


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("000000", "160000"),
        ("160000", "160000"),
        ("160000", "000000"),
        ("000000", "120000"),
        ("100644", "120000"),
        ("100644", "100755"),
        ("100755", "100644"),
    ],
)
def test_a_submodule_a_link_or_a_mode_change_is_not_plain(before: str, after: str) -> None:
    assert not plain(raw("100644", "100644", "src/a.py") + raw(before, after, "x"))


def test_a_path_that_starts_with_a_colon_is_a_path_not_a_header() -> None:
    assert plain(raw("100644", "100644", ":notes.txt"))
    assert not plain(raw("100644", "160000", ":notes.txt"))


def test_a_raw_record_without_its_modes_is_not_plain() -> None:
    assert not plain(":100644\0src/a.py\0")


def test_the_note_lists_each_blocking_finding_by_id_severity_and_words() -> None:
    blocking = [
        BlockingFinding(id="F1", severity="blocker", text="src/a.py:3 drops the lock"),
        BlockingFinding(id="F3", severity="major", text="CF-1-R2 has no test"),
    ]

    assert findings_note(blocking) == (
        "Review before merge: F1 [blocker] src/a.py:3 drops the lock; "
        "F3 [major] CF-1-R2 has no test"
    )


def test_the_first_sensitive_file_is_named_before_any_size() -> None:
    assert change_hold([(1, CONFIG)], 400, []) == (
        f"Sensitive path: {CONFIG} is the repository's config"
    )
    assert change_hold([(1, "Scripts/gate.sh")], None, ["scripts/**"]) == (
        "Sensitive path: Scripts/gate.sh matches scripts/**"
    )


def test_a_large_change_is_held_past_the_limit_and_not_at_it() -> None:
    assert change_hold([(200, "a.py"), (200, "b.py")], 400, []) is None
    assert change_hold([(200, "a.py"), (201, "b.py")], 400, []) == (
        "Large change: 401 changed lines, over large_change 400"
    )


def test_a_size_that_cannot_be_counted_is_held_against_the_limit() -> None:
    assert change_hold([(None, "shot.png")], 400, []) == (
        "Large change: its size cannot be counted, against large_change 400"
    )


def test_no_limit_and_no_sensitive_file_holds_nothing() -> None:
    assert change_hold([(10_000, "a.py")], None, []) is None


BLOCKING = [BlockingFinding(id="F1", severity="major", text="drops the lock")]


def decide(**more: Any) -> Hold | None:  # noqa: ANN401  # the facts to change
    base: dict[str, Any] = {
        "review_on": True,
        "small": False,
        "passed": False,
        "blocking": [],
        "ended": False,
        "skipped_note": None,
        "ready_since": NOW - timedelta(seconds=10),
        "run_timeout": 600,
        "review_active": False,
        "now": NOW,
        "head": "0123456789abcdef",
    }
    return review_hold_decision(**{**base, **more})


def held(**more: Any) -> Hold:  # noqa: ANN401  # the facts to change
    hold = decide(**more)
    assert hold is not None
    return hold


def test_nothing_holds_when_no_review_is_asked_or_the_diff_is_small_or_a_pass_stands() -> None:
    assert decide(review_on=False) is None
    assert decide(small=True) is None
    assert decide(passed=True) is None


def test_a_pass_with_a_blocking_finding_open_waits_on_the_owner_with_the_findings_note() -> None:
    hold = held(passed=True, blocking=BLOCKING)

    assert (hold.reason, hold.owner) == ("Review before merge: F1 [major] drops the lock", True)


def test_a_review_that_ended_with_a_blocking_finding_names_the_finding() -> None:
    hold = held(ended=True, blocking=BLOCKING)

    assert hold.reason == "Review before merge: F1 [major] drops the lock"


def test_a_review_that_ended_without_a_pass_waits_on_the_owner() -> None:
    hold = held(ended=True)

    assert (hold.reason, hold.owner) == (
        "Review before merge: the review of 0123456 ended without a pass",
        True,
    )


def test_a_skipped_review_names_its_note() -> None:
    hold = held(skipped_note="budget spent")

    assert (hold.reason, hold.owner) == (
        "Review before merge: the review of 0123456 was skipped (budget spent)",
        True,
    )


def test_a_review_that_ended_outranks_a_skip_record() -> None:
    assert held(ended=True, skipped_note="x").reason.endswith("ended without a pass")


def test_a_head_that_waited_past_the_run_timeout_with_no_review_running_waits_on_the_owner() -> (
    None
):
    hold = held(ready_since=NOW - timedelta(seconds=601))

    assert (hold.reason, hold.owner) == (
        "Review before merge: no review of 0123456 ended within 600 s",
        True,
    )


def test_the_timeout_is_not_late_at_the_limit_itself() -> None:
    hold = held(ready_since=NOW - timedelta(seconds=600))

    assert (hold.reason, hold.owner) == (
        "Review before merge: waits for the review of 0123456",
        False,
    )


def test_a_head_no_record_dates_has_waited_an_unknown_time_which_is_late() -> None:
    assert held(ready_since=None).owner is True


def test_a_late_head_with_a_review_running_still_waits_for_it() -> None:
    hold = held(ready_since=NOW - timedelta(seconds=9999), review_active=True)

    assert (hold.reason, hold.owner) == (
        "Review before merge: waits for the review of 0123456",
        False,
    )


def test_a_blocking_finding_with_no_review_of_this_head_does_not_name_findings_alone() -> None:
    hold = held(blocking=BLOCKING)

    assert hold.owner is False


@pytest.mark.parametrize(
    ("verdict", "blocking", "returned", "outcome"),
    [
        ("pass", False, 0, "pass"),
        ("pass", False, 9, "pass"),
        ("changes", False, 0, "changes"),
        ("pass", True, 0, "changes"),
        ("changes", True, 2, "changes"),
        ("changes", False, 3, "halt"),
        ("pass", True, 3, "halt"),
        ("changes", False, 4, "halt"),
    ],
)
def test_a_review_passes_returns_the_ticket_or_halts_at_the_round_cap(
    verdict: str, blocking: bool, returned: int, outcome: str
) -> None:
    assert review_outcome(verdict, blocking_open=blocking, returned=returned, cap=3) == outcome
