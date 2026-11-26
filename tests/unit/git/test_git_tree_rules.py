"""Tree validation, guards, landing words."""

import pytest

from code_factory.git.models import FolderSnapshot, Redirected, TreeFolders, TreeKind, TreeRecord
from code_factory.git.rules.folders import (
    board_tree_of,
    fast_forward_merge,
    guarded,
    kept_paths,
    validate_tree,
)
from code_factory.git.rules.landing import choose_landing_head, lost_words

TOKEN = "0123456789abcdef0123456789abcdef"  # noqa: S105
T = "/r/.code-factory/worktrees/CF-1"


def _record(kind: TreeKind) -> TreeRecord:
    return TreeRecord(
        repository="r",
        name="CF-1",
        kind=kind,
        ticket_id="CF-1",
        attempt=0,
        branch="b",
        path=T,
        token=TOKEN,
    )


def _clone(**over: object) -> FolderSnapshot:
    base = {
        "resolved_path": T,
        "dot_git_kind": "dir",
        "dot_git_resolved": f"{T}/.git",
        "info_resolved": f"{T}/.git/objects/info",
        "alternates_resolved": f"{T}/.git/objects/info/alternates",
        "alternates_text": "",
        "alternates_exists": True,
        "token_text": TOKEN + "\n",
    }
    return FolderSnapshot.model_validate({**base, **over})


def _worktree(**over: object) -> FolderSnapshot:
    admin = "/r/.git/worktrees/CF-1"
    base = {
        "resolved_path": T,
        "dot_git_kind": "file",
        "dot_git_resolved": f"{T}/.git",
        "dot_git_text": f"gitdir: {admin}\n",
        "admin_resolved": admin,
        "gitdir_text": f"{T}/.git\n",
        "commondir_text": "../..\n",
        "common_dir": "/r/.git",
    }
    return FolderSnapshot.model_validate({**base, **over})


def test_the_exact_clone_and_worktree_layouts_are_accepted() -> None:
    clone = validate_tree(_clone(), _record(TreeKind.CLONE))
    assert isinstance(clone, TreeFolders)
    assert clone.is_clone
    worktree = validate_tree(_worktree(), _record(TreeKind.WORKTREE))
    assert isinstance(worktree, TreeFolders)
    assert not worktree.is_clone


@pytest.mark.parametrize(
    "over",
    [
        {"dot_git_kind": "link"},
        {"dot_git_resolved": "/elsewhere/.git"},
        {"commondir_exists": True},
        {"alternates_text": "/x/objects\n"},
        {"alternates_resolved": "/x/alternates"},
        {"info_resolved": "/x/info"},
        {"token_text": "f" * 32 + "\n"},
        {"token_text": None},
        {"nested_git": True},
    ],
)
def test_each_clone_deviation_is_refused(over: dict[str, object]) -> None:
    assert isinstance(validate_tree(_clone(**over), _record(TreeKind.CLONE)), Redirected)


@pytest.mark.parametrize(
    "over",
    [
        {"dot_git_text": "gitdir: /r/.git/worktrees/CF-1"},
        {"dot_git_text": "gitdir: ../x\n"},
        {"admin_resolved": "/other"},
        {"gitdir_text": "/x/.git\n"},
        {"commondir_text": "..\n"},
        {"common_dir": "/other/.git"},
        {"dot_git_kind": "dir"},
        {"nested_git": True},
    ],
)
def test_each_worktree_deviation_is_refused(over: dict[str, object]) -> None:
    assert isinstance(validate_tree(_worktree(**over), _record(TreeKind.WORKTREE)), Redirected)


def test_a_missing_record_is_refused() -> None:
    assert isinstance(validate_tree(_clone(), None), Redirected)


def test_an_absent_alternates_file_is_fine() -> None:
    assert isinstance(
        validate_tree(
            _clone(alternates_text=None, alternates_exists=False), _record(TreeKind.CLONE)
        ),
        TreeFolders,
    )


def test_kept_paths_count_four_for_a_clone_and_seven_for_a_worktree() -> None:
    clone = validate_tree(_clone(), _record(TreeKind.CLONE))
    worktree = validate_tree(_worktree(), _record(TreeKind.WORKTREE))
    assert isinstance(clone, TreeFolders)
    assert isinstance(worktree, TreeFolders)
    assert len(kept_paths(clone)) == 4
    assert len(kept_paths(worktree)) == 7


def test_guards_only_in_a_board_tree_and_submodule_flag_only_on_four_commands() -> None:
    assert guarded(["status"], in_tree=False) == ["status"]
    assert guarded(["log"], in_tree=True) == [
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "diff.ignoreSubmodules=all",
        "log",
    ]
    assert "--ignore-submodules=all" in guarded(["status", "-s"], in_tree=True)
    assert "--ignore-submodules=all" not in guarded(["log"], in_tree=True)
    assert fast_forward_merge("x")[-3:] == ["--ff-only", "--end-of-options", "x"]
    assert "diff.ignoreSubmodules=all" not in fast_forward_merge("x")


def test_board_tree_of_is_the_innermost_tree() -> None:
    assert board_tree_of(f"{T}/src/a") == ("/r", T)
    assert board_tree_of("/r/src") is None
    assert board_tree_of("/r/.code-factory/worktrees") is None


def test_lost_words_name_ten_then_count_the_rest() -> None:
    files = [f"f{n}" for n in range(12)]
    assert lost_words(files, ["abc one"]) == (
        "12 uncommitted files (f0, f1, f2, f3, f4, f5, f6, f7, f8, f9, and 2 more) "
        "and 1 unmerged commit (abc one)"
    )
    assert lost_words([], []) is None
    assert lost_words(["a"], []) == "1 uncommitted file (a)"


def test_landing_head_cases() -> None:
    held = choose_landing_head(
        clone_tip="c",
        clone_holds_main=True,
        pushed="p",
        pushed_is_ours=True,
        first_holds_main=False,
    )
    assert held.head == "c"
    foreign = choose_landing_head(
        clone_tip="c",
        clone_holds_main=False,
        pushed="p",
        pushed_is_ours=False,
        first_holds_main=False,
    )
    assert (foreign.first, foreign.head) == ("c", None)
    ours = choose_landing_head(
        clone_tip="c",
        clone_holds_main=False,
        pushed="p",
        pushed_is_ours=True,
        first_holds_main=False,
    )
    assert (ours.first, ours.head) == ("p", None)
    done = choose_landing_head(
        clone_tip="c",
        clone_holds_main=False,
        pushed="p",
        pushed_is_ours=True,
        first_holds_main=True,
    )
    assert done.head == "p"
