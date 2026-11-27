"""One ticket's branch facts from the facts git read of its repository. Expected values: the
previous implementation's merged-at-the-remote-tip test and the delivery golden's facts (a pull
request merge, a squash commit, a commit whose body only names another ticket, a ticket id that is
a prefix of another)."""

from code_factory.git.models import GitFacts
from code_factory.stages.models import BranchFacts
from code_factory.stages.rules import branch_facts

LOG = (
    "Notes about CF-8 in the body only\n"
    "CF-100: another ticket\n"
    "CF-7: squash the feature (#7)\n"
    "Merge pull request #6 from feat/CF-6"
)


def repo(**more: object) -> GitFacts:
    base: dict[str, object] = {
        "default_branch": "main",
        "local": frozenset({"main", "feat/CF-1", "feat/CF-4", "feat/CF-6"}),
        "remote": frozenset({"main", "feat/CF-1"}),
        "tips": {
            "main": "M2",
            "feat/CF-1": "A1",
            "feat/CF-4": "R",
            "feat/CF-6": "S6",
            "origin/main": "M2",
            "origin/feat/CF-1": "A1",
        },
        "merged_in": frozenset({"S6"}),
        "main_line": frozenset({"M2", "M1", "c7", "mm6", "R"}),
        "log": LOG,
        "merged_heads": frozenset({"feat/CF-6", "CF-6"}),
        "known": True,
    }
    return GitFacts.model_validate({**base, **more})


def facts(ticket: str, branch: str, git: GitFacts | None = None) -> BranchFacts:
    return branch_facts(ticket, branch, git or repo(), worktrees=frozenset())


def test_a_branch_merged_by_a_pull_request_merge_is_merged() -> None:
    assert facts("CF-6", "feat/CF-6").merged


def test_a_branch_with_a_commit_of_its_own_is_started_pushed_and_built() -> None:
    found = facts("CF-1", "feat/CF-1")

    assert (found.local, found.pushed, found.has_commits, found.merged) == (True, True, True, False)
    assert (found.known, found.head, found.default_branch) == (True, "A1", "main")


def test_a_branch_cut_from_main_with_no_commit_holds_none_of_its_own() -> None:
    found = facts("CF-4", "feat/CF-4")

    assert (found.local, found.has_commits, found.merged) == (True, False, False)


def test_a_fast_forward_lands_the_ticket_whose_branch_tip_names_it() -> None:
    git = repo(main_subjects={"R": "CF-4 Place the test at the repository root"})
    assert facts("CF-4", "feat/CF-4", git).merged
    assert not facts("CF-40", "feat/CF-4", git).merged
    assert not facts("CF-4", "main", git).merged


def test_a_matching_remote_tip_cannot_hide_new_commits_on_the_local_branch() -> None:
    git = repo(
        tips={"main": "M2", "feat/CF-1": "A1", "origin/feat/CF-1": "R"},
        main_subjects={"R": "CF-1 Implement the first change"},
    )
    assert not facts("CF-1", "feat/CF-1", git).merged


def test_a_ticket_with_no_branch_is_not_started() -> None:
    found = facts("CF-10", "")

    flags = (found.local, found.pushed, found.merged, found.has_commits)
    assert flags == (False,) * 4
    assert found.untraced == ""


def test_a_squash_commit_naming_the_ticket_lands_it_when_its_branch_is_gone() -> None:
    assert facts("CF-7", "feat/CF-7").merged


def test_a_longer_ticket_number_or_a_body_only_mention_lands_nothing() -> None:
    longer = repo(log="CF-70x: not CF-7")

    assert not facts("CF-7", "feat/CF-7", longer).merged
    assert not facts("CF-8", "feat/CF-8").merged
    assert not facts("CF-10", "feat/CF-10").merged


def test_work_that_cannot_be_traced_says_why_with_the_branch_the_default_and_the_limit() -> None:
    assert facts("CF-8", "feat/CF-8").untraced == (
        "feat/CF-8 has no local or remote branch here, and main holds no pull request merge of it "
        "nor, in its last 1000 commits, a commit starting with CF-8 that landed work"
    )


def test_a_branch_with_a_tip_is_never_untraced_and_a_merged_one_neither() -> None:
    assert facts("CF-1", "feat/CF-1").untraced == ""
    assert facts("CF-7", "feat/CF-7").untraced == ""


def test_a_branch_merged_at_its_remote_tip_is_merged_though_its_local_one_is_behind() -> None:
    git = repo(
        local=frozenset({"main", "feat/x"}),
        remote=frozenset({"feat/x"}),
        tips={"main": "m1", "feat/x": "old", "origin/feat/x": "new"},
        merged_in=frozenset({"new"}),
        main_line=frozenset(),
        log="",
        merged_heads=frozenset(),
    )

    assert facts("CF-1", "feat/x", git).merged
    assert not facts("CF-2", "feat/y", git).merged


def test_a_branch_named_by_a_merge_title_is_merged_when_it_has_no_tip() -> None:
    git = repo(log="", merged_heads=frozenset({"feat/CF-3"}))

    assert facts("CF-3", "feat/CF-3", git).merged


def test_nothing_reads_as_merged_or_traced_while_a_git_read_failed() -> None:
    found = facts("CF-6", "feat/CF-6", repo(known=False))

    assert (found.known, found.merged, found.untraced) == (False, False, "")


def test_a_branch_checked_out_in_a_board_tree_is_in_a_worktree() -> None:
    found = branch_facts("CF-9", "feat/CF-9", repo(), worktrees=frozenset({"feat/CF-9"}))

    assert found.in_worktree
    assert not facts("CF-9", "feat/CF-9").in_worktree
