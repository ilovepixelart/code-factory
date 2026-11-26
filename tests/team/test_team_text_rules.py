"""The words a card says, path overlap, gate progress, first commits and the cycle.

Expected values: the team spec's hand cases and the previous implementation's tests of the gate
log vocabulary, first commits and the cycle.
"""

import pytest

from code_factory.team.rules import (
    CONTAINER_WAIT,
    cycle_since,
    first_commits,
    gate_line,
    gate_progress,
    hold_summary,
    named_paths,
    overlap,
    queue_note,
    subagent_ticket,
)
from team_values import NOW

DAY = 86_400.0


@pytest.mark.parametrize(
    ("missing", "expected"),
    [
        (("requirements",), "requirements"),
        (("mock",), "mock"),
        (("uat",), "UAT"),
        (("requirements", "mock"), "requirements and mock"),
        (("uat", "requirements"), "requirements and UAT"),
        (("requirements", "mock", "spec"), "requirements, mock and spec"),
        (("uat", "spec", "mock", "requirements"), "requirements, mock, spec and UAT"),
        (("requirements", "review"), "requirements"),
    ],
)
def test_a_spec_hold_names_the_missing_documents_in_writing_order(
    missing: tuple[str, ...], expected: str
) -> None:
    assert hold_summary("spec", "the detail", missing) == expected


@pytest.mark.parametrize(
    ("stage", "missing"),
    [("build", ("requirements",)), ("spec", ()), ("spec", ("review", "notes"))],
)
def test_any_other_hold_keeps_its_detail(stage: str, missing: tuple[str, ...]) -> None:
    assert hold_summary(stage, "a branch", missing) == "a branch"


def test_named_paths_are_the_path_like_words_trimmed_sorted_and_unique() -> None:
    text = "Change src/a/b.py and the README.md. See docs/, src/a/b.py and also ./x/y/ today"
    assert named_paths(text) == ["README.md", "docs", "src/a/b.py", "x/y"]


def test_a_word_with_neither_a_slash_nor_a_dot_is_no_path() -> None:
    assert named_paths("fix the login flow") == []


OPEN = [("#12", ["src/a/x.py", "docs/guide.md"]), ("#13", ["src/a/y.py"])]


def test_an_open_change_overlaps_a_ticket_naming_its_file_or_a_folder_above_it() -> None:
    assert overlap(["docs/guide.md"], OPEN) == "likely overlaps #12 in docs/guide.md"
    assert overlap(["src/a"], OPEN) == "likely overlaps #12 in src/a/x.py"


def test_the_first_open_change_with_a_match_wins() -> None:
    assert overlap(["src/a/y.py", "src/a/x.py"], OPEN) == "likely overlaps #12 in src/a/x.py"


def test_a_name_that_only_starts_like_a_folder_is_no_overlap() -> None:
    assert overlap(["src/a"], [("#1", ["src/ab/x.py"])]) is None
    assert overlap(["other"], OPEN) is None


@pytest.mark.parametrize(
    ("note", "reason", "expected"),
    [
        ("likely overlaps #12 in a", "", "next, likely overlaps #12 in a"),
        ("likely overlaps #12 in a", "writer 1 of 1 tokens", "writer 1 of 1 tokens"),
        ("", "", ""),
        ("", "held", "held"),
    ],
)
def test_the_queue_note_is_the_cap_reason_else_next_with_the_overlap(
    note: str, reason: str, expected: str
) -> None:
    assert queue_note(note, reason) == expected


TREE = "/repo/trees/CF-9"
OTHER = "/repo/trees/CF-6"
LOG = "gate: preflight passed in 1s\ngate: rust-format passed in 1s\n"
WAITS = (
    "gate: rust-lint waits for the heavy-step lock, held by pid 77: "
    f"rust-test in {OTHER} on ticket/cf-6\n"
)


def test_a_gate_holding_the_lock_names_its_step() -> None:
    progress = gate_progress(LOG, f"29529 rust-lint in {TREE} on ticket/cf-9", TREE)
    assert (progress.step, progress.holds_lock, progress.waiting) == ("rust-lint", True, False)
    assert gate_line(progress) == "rust-lint, holding the heavy-step lock"


def test_a_gate_waiting_names_the_holder_by_its_tree_folder_and_step() -> None:
    held = f"77 rust-test in {OTHER} on ticket/cf-6"
    progress = gate_progress(LOG + WAITS, held, TREE)
    assert (progress.step, progress.holds_lock, progress.waiting) == ("rust-lint", False, True)
    assert gate_line(progress) == "waiting for the heavy-step lock behind CF-6 (rust-test)"


def test_a_wait_with_no_known_holder_still_says_it_waits() -> None:
    progress = gate_progress(
        "gate: rust-lint waits for the heavy-step lock, held by pid 77\n", None, TREE
    )
    assert gate_line(progress) == "waiting for the heavy-step lock"


def test_a_gate_that_got_the_lock_it_waited_for_no_longer_waits() -> None:
    log = LOG + WAITS + "gate: rust-lint waited 9s for the heavy-step lock\n"
    progress = gate_progress(log, None, TREE)
    assert (gate_line(progress), progress.behind) == ("after rust-format passed", None)


def test_a_gate_that_runs_without_the_lock_no_longer_waits() -> None:
    held = f"pid 77: rust-test in {OTHER} on ticket/cf-6"
    log = (
        "gate: rust-format passed in 1s\n"
        f"gate: rust-lint waits for the heavy-step lock, held by {held}\n"
        f"gate: rust-lint runs without the heavy-step lock: {held} held it over 1800s\n"
    )
    progress = gate_progress(log, held.removeprefix("pid ").replace(":", ""), TREE)
    assert (gate_line(progress), progress.waiting, progress.holds_lock) == (
        "after rust-format passed",
        False,
        False,
    )


def test_a_gate_with_no_log_is_starting() -> None:
    assert gate_line(gate_progress("", None, TREE)) == "starting"


def test_the_step_a_log_says_started_is_the_gates_step_until_it_passes() -> None:
    light = "gate: preflight passed in 1s\ngate: web-lint starts\n"
    started = gate_progress(light, None, TREE)
    passed = gate_progress(light + "gate: web-lint passed in 4s\n", None, TREE)
    assert (started.step, gate_line(started), started.waiting) == ("web-lint", "web-lint", False)
    assert (passed.step, gate_line(passed)) == (None, "after web-lint passed")


def test_a_heavy_step_that_started_after_its_wait_is_running_not_waiting() -> None:
    heavy = (
        LOG + WAITS + "gate: rust-lint waited 9s for the heavy-step lock\ngate: rust-lint starts\n"
    )
    assert gate_line(gate_progress(heavy, None, TREE)) == "rust-lint"
    holding = gate_progress(heavy, f"29529 rust-lint in {TREE} on ticket/cf-9", TREE)
    assert gate_line(holding) == "rust-lint, holding the heavy-step lock"


def test_a_later_wait_after_a_pass_is_still_a_wait() -> None:
    log = "gate: web-lint starts\ngate: web-lint passed in 4s\n" + WAITS
    assert gate_line(gate_progress(log, None, TREE)) == (
        "waiting for the heavy-step lock behind CF-6 (rust-test)"
    )


def test_a_line_that_only_ends_like_a_start_names_no_step() -> None:
    log = (
        "gate: preflight passed in 1s\n"
        "gate: rust-test runs every test: the server starts\ngate: starts\n"
    )
    progress = gate_progress(log, None, TREE)
    assert (progress.step, gate_line(progress)) == (None, "after preflight passed")


def test_checks_waiting_for_a_container_wait_until_the_gates_own_lines_follow() -> None:
    queued = gate_progress(CONTAINER_WAIT + "\n", None, TREE)
    begun = gate_progress(
        CONTAINER_WAIT + "\ngate: web checks skipped: nothing changed\n", None, TREE
    )
    running = gate_progress(CONTAINER_WAIT + "\ngate: preflight starts\n", None, TREE)
    assert (queued.waiting, queued.step, gate_line(queued)) == (
        True,
        None,
        "waiting for a checks container's turn",
    )
    assert (begun.waiting, gate_line(begun)) == (False, "starting")
    assert (running.waiting, gate_line(running)) == (False, "preflight")


def test_a_ticket_is_the_worktree_the_newest_tool_call_names() -> None:
    marker = ".code-factory/worktrees/"
    calls = [
        f"/Users/a/repo/{marker}CF-12/web/src/pages/TeamPage.vue",
        f"cd /Users/a/repo/{marker}CF-8 && ls",
    ]
    assert subagent_ticket(calls, marker) == "CF-12"
    assert subagent_ticket([f"cd /r/{marker}CF-8"], marker) == "CF-8"
    assert subagent_ticket(["ls", ""], marker) is None
    assert subagent_ticket([f"cd /r/{marker}"], marker) is None


def test_a_first_commit_is_the_earliest_subject_starting_with_the_ticket_id() -> None:
    log = (
        "100\tCF-7: requirements\n300\tCF-7: Build it\n200\tCF-8: spec\n"
        "50\tMerge pull request #3 from x/CF-7\n90\tCF-70: other\nnoise\nx\tCF-9: bad time\n"
    )
    assert first_commits(log) == {"CF-7": 100.0, "CF-8": 200.0, "CF-70": 90.0}


def test_the_cycle_is_seven_days_until_a_release_tag_exists_then_since_the_newest() -> None:
    none = cycle_since(NOW, [])
    assert (none.since, none.from_) == (NOW - 7 * DAY, "the last 7 days")
    tags = [("v0.1.0", NOW - 9 * DAY), ("v0.2.0", NOW - 2 * DAY), ("nightly", NOW - DAY)]
    tagged = cycle_since(NOW, tags)
    assert (tagged.since, tagged.from_) == (NOW - 2 * DAY, "since v0.2.0")


def test_a_tag_after_now_and_a_tag_not_naming_a_release_are_ignored() -> None:
    tags = [("v1.0", 100.0), ("v2.0", 200.0), ("beta", 300.0), ("rev2", 350.0)]
    assert cycle_since(250.0, tags).from_ == "since v2.0"
    assert cycle_since(400.0, tags).from_ == "since v2.0"
    assert cycle_since(150.0, tags).from_ == "since v1.0"
    assert cycle_since(50.0, tags).from_ == "the last 7 days"


def test_a_tag_made_at_the_moment_of_now_starts_the_cycle() -> None:
    cycle = cycle_since(200.0, [("v1.0", 100.0), ("v2.0", 200.0)])
    assert (cycle.since, cycle.from_) == (200.0, "since v2.0")
    assert cycle_since(199.0, [("v1.0", 100.0), ("v2.0", 200.0)]).from_ == "since v1.0"
    assert cycle_since(400.0, [("vnext", 300.0)]).from_ == "the last 7 days"
