"""Hand landing and removing a worktree, with real git and a bare origin."""

from pathlib import Path

import anyio
import pytest

from code_factory.git.models import Conflicted, Current, Merged, NotMerged, Refused, Updated
from code_factory.git.service import GitService
from code_factory.platform.errors import ConflictError, NotFoundError
from git_support import Fakes, commit, git, ticket_ref, write

ORIGIN = "sample-origin.git"


@pytest.fixture
async def clone(service: GitService, root: Path, fakes: Fakes) -> Path:
    fakes.tickets["CF-1"] = ticket_ref(branch="ticket/cf-1")
    await service.start_worktree("sample", "CF-1")
    return root / ".code-factory/worktrees/CF-1"


def origin_of(root: Path) -> Path:
    return root.parent / ORIGIN


async def test_a_land_in_a_clone_merges_through_the_main_checkout(
    service: GitService, clone: Path, root: Path, fakes: Fakes
) -> None:
    tip = commit(clone, "Clone work", **{"c.txt": "c\n"})
    landed = await service.land("sample", "CF-1")
    assert isinstance(landed, Merged)
    assert landed.url.startswith("https://example.test/pull/1")
    assert git(origin_of(root), "rev-parse", "refs/heads/ticket/cf-1") == tip
    assert fakes.forge.opened == [
        {"branch": "ticket/cf-1", "head": tip, "base": "main", "title": "CF-1: A ticket"}
    ]
    assert fakes.forge.merged == [tip]
    assert not await anyio.Path(clone).exists()  # the clone is removed after the merge


async def test_main_moving_again_builds_a_merge_commit_and_a_second_land_builds_on_the_pushed_head(
    service: GitService, clone: Path, root: Path, fakes: Fakes
) -> None:
    clone_tip = commit(clone, "Clone work", **{"c.txt": "c\n"})
    other = root.parent / "other"
    git(root.parent, "clone", "-q", str(origin_of(root)), str(other))
    main_tip = commit(other, "Main moved", **{"m.txt": "m\n"})
    git(other, "push", "-q", "origin", "main")
    fakes.forge.state = "blocked"
    first = await service.land("sample", "CF-1")
    assert isinstance(first, NotMerged)
    assert first.why == "blocked"
    pushed = git(origin_of(root), "rev-parse", "refs/heads/ticket/cf-1")
    assert pushed not in {clone_tip, main_tip}
    assert git(root, "rev-parse", f"{pushed}^1") == clone_tip
    assert git(root, "rev-parse", f"{pushed}^2") == main_tip
    main_again = commit(other, "Main moved twice", **{"n.txt": "n\n"})
    git(other, "push", "-q", "origin", "main")
    fakes.forge.state = "clean"
    second = await service.land("sample", "CF-1")
    assert isinstance(second, Merged)
    head = git(origin_of(root), "rev-parse", "refs/heads/ticket/cf-1")
    assert git(root, "rev-parse", f"{head}^1") == pushed  # built on the pushed head
    assert git(root, "rev-parse", f"{head}^2") == main_again


async def test_a_commit_pushed_from_elsewhere_is_not_reused_as_the_head(
    service: GitService, clone: Path, root: Path, fakes: Fakes
) -> None:
    clone_tip = commit(clone, "Clone work", **{"c.txt": "c\n"})
    other = root.parent / "other"
    git(root.parent, "clone", "-q", str(origin_of(root)), str(other))
    commit(other, "Main moved", **{"m.txt": "m\n"})
    git(other, "push", "-q", "origin", "main")
    git(other, "fetch", "-q", "origin")
    foreign = commit(clone, "Foreign", **{"f.txt": "f\n"})
    git(clone, "push", "-q", str(origin_of(root)), f"{foreign}:refs/heads/ticket/cf-1")
    git(clone, "reset", "-q", "--hard", clone_tip)
    landed = await service.land("sample", "CF-1")
    # The foreign commit is not the head: the merge is built on the clone's tip, and the push of
    # that head is refused because it does not contain the foreign commit. Nothing is forced.
    assert isinstance(landed, Refused)
    assert "the push of ticket/cf-1 failed" in landed.why
    assert git(origin_of(root), "rev-parse", "refs/heads/ticket/cf-1") == foreign
    assert fakes.forge.opened == []
    assert clone_tip != foreign


async def test_conflicts_name_the_files_and_leave_the_branch_as_it_was(
    service: GitService, clone: Path, root: Path
) -> None:
    clone_tip = commit(clone, "Clone work", **{"readme.md": "clone\n"})
    other = root.parent / "other"
    git(root.parent, "clone", "-q", str(origin_of(root)), str(other))
    commit(other, "Main edits", **{"readme.md": "main\n"})
    git(other, "push", "-q", "origin", "main")
    landed = await service.land("sample", "CF-1")
    assert landed == Conflicted(files=["readme.md"])
    assert (
        git(origin_of(root), "rev-parse", "--verify", "-q", "refs/heads/ticket/cf-1", check=False)
        == ""
    )
    assert git(clone, "rev-parse", "HEAD") == clone_tip


async def test_a_hook_of_the_repository_does_not_run_when_a_worktree_merges_main_in(
    service: GitService, root: Path
) -> None:
    await service.start_worktree("sample", "CF-1", owner_by_hand=True)
    tree = root / ".code-factory/worktrees/CF-1"
    commit(tree, "Hand work", **{"h.txt": "h\n"})
    other = root.parent / "other"
    git(root.parent, "clone", "-q", str(origin_of(root)), str(other))
    commit(other, "Main moved", **{"m.txt": "m\n"})
    git(other, "push", "-q", "origin", "main")
    git(root, "config", "core.hooksPath", str(root / ".git/hooks"))  # outranks a global one
    marker = root.parent / "pre-merge-commit-ran"
    hook = root / ".git/hooks/pre-merge-commit"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
    hook.chmod(0o755)
    assert isinstance(await service.land("sample", "CF-1"), Merged)
    assert not marker.exists()


async def test_a_branch_ref_that_names_a_tree_is_refused_not_landed(
    service: GitService, clone: Path, fakes: Fakes
) -> None:
    commit(clone, "Clone work", **{"c.txt": "c\n"})
    tree = git(clone, "rev-parse", "HEAD^{tree}")
    (clone / ".git/refs/heads/ticket/cf-1").write_text(f"{tree}\n")  # update-ref refuses a tree
    landed = await service.land("sample", "CF-1")
    assert isinstance(landed, Refused)
    assert fakes.forge.opened == []
    assert "not a commit" in landed.why


async def test_a_failing_validation_is_refused(service: GitService, clone: Path) -> None:
    (clone / ".git/objects/info/alternates").write_text("/x\n")
    landed = await service.land("sample", "CF-1")
    assert isinstance(landed, Refused)
    assert "not a clone or worktree the board made" in landed.why


async def test_pinned_refuses_once_the_tip_moves(service: GitService, clone: Path) -> None:
    pinned = commit(clone, "Judged", **{"c.txt": "c\n"})
    commit(clone, "Later", **{"d.txt": "d\n"})
    landed = await service.land("sample", "CF-1", pinned=pinned)
    assert isinstance(landed, NotMerged)
    assert landed.why.startswith(f"the tip moved from {pinned} to ")


async def test_a_pinned_land_still_merges_main_in_before_the_push(
    service: GitService, clone: Path, root: Path, fakes: Fakes
) -> None:
    pinned = commit(clone, "Judged", **{"c.txt": "c\n"})
    other = root.parent / "other"
    git(root.parent, "clone", "-q", str(origin_of(root)), str(other))
    main_tip = commit(other, "Main moved", **{"m.txt": "m\n"})
    git(other, "push", "-q", "origin", "main")
    fakes.forge.state = "blocked"
    landed = await service.land("sample", "CF-1", pinned=pinned)
    assert isinstance(landed, NotMerged)
    head = git(origin_of(root), "rev-parse", "refs/heads/ticket/cf-1")
    assert git(root, "rev-parse", f"{head}^1") == pinned
    assert git(root, "rev-parse", f"{head}^2") == main_tip


async def test_a_pinned_worktree_land_refuses_once_head_moves(
    service: GitService, root: Path
) -> None:
    await service.start_worktree("sample", "CF-1", owner_by_hand=True)
    tree = root / ".code-factory/worktrees/CF-1"
    pinned = commit(tree, "Judged", **{"h.txt": "h\n"})
    commit(tree, "Later", **{"i.txt": "i\n"})
    landed = await service.land("sample", "CF-1", pinned=pinned)
    assert isinstance(landed, NotMerged)
    assert landed.why.startswith(f"the tip moved from {pinned} to ")


async def test_configured_checks_gate_the_merge(
    service: GitService, clone: Path, fakes: Fakes
) -> None:
    commit(clone, "Clone work", **{"c.txt": "c\n"})
    fakes.checks_configured = True
    fakes.verdict_ = "missing"
    missing = await service.land("sample", "CF-1")
    assert isinstance(missing, NotMerged)
    assert missing.why.startswith("waits for the board's checks on ")
    fakes.verdict_ = "failed"
    failed = await service.land("sample", "CF-1")
    assert isinstance(failed, NotMerged)
    assert failed.why.startswith("the board's checks failed on ")
    assert fakes.forge.merged == []
    fakes.verdict_ = "passed"
    assert isinstance(await service.land("sample", "CF-1"), Merged)


async def test_the_default_branch_and_a_missing_tree_and_a_bad_id_are_refused(
    service: GitService, fakes: Fakes
) -> None:
    assert await service.land("sample", "CF-1") == Refused(why="no tree CF-1 for sample")
    assert await service.land("sample", "../x") == Refused(why="../x is not a ticket id")
    fakes.tickets["CF-2"] = ticket_ref("CF-2", branch="main")
    await service.start_worktree("sample", "CF-2")
    landed = await service.land("sample", "CF-2")
    assert isinstance(landed, Refused)


async def test_a_worktree_land_merges_main_in_and_pushes(service: GitService, root: Path) -> None:
    await service.start_worktree("sample", "CF-1", owner_by_hand=True)
    tree = root / ".code-factory/worktrees/CF-1"
    commit(tree, "Hand work", **{"h.txt": "h\n"})
    other = root.parent / "other"
    git(root.parent, "clone", "-q", str(origin_of(root)), str(other))
    commit(other, "Main moved", **{"m.txt": "m\n"})
    git(other, "push", "-q", "origin", "main")
    landed = await service.land("sample", "CF-1")
    assert isinstance(landed, Merged)
    assert (await service.list_trees("sample")) == []


async def test_a_worktree_land_conflict_names_files_and_aborts_the_merge(
    service: GitService, root: Path
) -> None:
    await service.start_worktree("sample", "CF-1", owner_by_hand=True)
    tree = root / ".code-factory/worktrees/CF-1"
    commit(tree, "Hand edit", **{"readme.md": "hand\n"})
    other = root.parent / "other"
    git(root.parent, "clone", "-q", str(origin_of(root)), str(other))
    commit(other, "Main edit", **{"readme.md": "main\n"})
    git(other, "push", "-q", "origin", "main")
    assert await service.land("sample", "CF-1") == Conflicted(files=["readme.md"])
    assert git(tree, "status", "--porcelain") == ""  # the merge was aborted


async def test_remove_worktree_refuses_to_lose_work_and_removes_a_clean_merged_one(
    service: GitService, root: Path
) -> None:
    await service.start_worktree("sample", "CF-1", owner_by_hand=True)
    tree = root / ".code-factory/worktrees/CF-1"
    write(tree, "new.txt", "x\n")
    with pytest.raises(ConflictError, match=r"CF-1 holds 1 uncommitted file \(new.txt\)"):
        await service.remove_worktree("sample", "CF-1")
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", "Hand work")
    with pytest.raises(
        ConflictError, match=r"1 unmerged commit \([0-9a-f]+ Hand work\).*code-factory save CF-1"
    ):
        await service.remove_worktree("sample", "CF-1")
    git(tree, "reset", "-q", "--hard", "origin/main")
    removed = await service.remove_worktree("sample", "CF-1")
    assert (removed.branch, removed.branch_deleted) == ("ticket/cf-1", True)
    assert not tree.exists()
    assert git(root, "branch", "--list", "ticket/cf-1") == ""


@pytest.mark.usefixtures("clone")
async def test_remove_worktree_never_takes_a_clone_or_an_unknown_name(service: GitService) -> None:
    with pytest.raises(NotFoundError):
        await service.remove_worktree("sample", "CF-1")
    with pytest.raises(NotFoundError):
        await service.remove_worktree("sample", "nope")


async def test_update_branch_merges_main_into_the_branch_or_names_conflicts(
    service: GitService, root: Path, fakes: Fakes
) -> None:

    git(root, "checkout", "-q", "-b", "ticket/cf-1")
    commit(root, "Work", **{"w.txt": "w\n"})
    git(root, "checkout", "-q", "main")
    fakes.tickets["CF-1"] = ticket_ref(branch="ticket/cf-1")
    other = root.parent / "other"
    git(root.parent, "clone", "-q", str(origin_of(root)), str(other))
    main_tip = commit(other, "Main moved", **{"m.txt": "m\n"})
    git(other, "push", "-q", "origin", "main")
    git(root, "fetch", "-q", "origin")
    updated = await service.update_branch("sample", "CF-1")
    assert isinstance(updated, Updated)
    assert git(root, "rev-parse", f"{updated.tip}^2") == main_tip
    assert git(root, "rev-parse", "ticket/cf-1") == updated.tip
    assert await service.update_branch("sample", "CF-1") == Current()
    commit(other, "Conflict", **{"w.txt": "other\n"})
    git(other, "push", "-q", "origin", "main")
    git(root, "fetch", "-q", "origin")
    assert await service.update_branch("sample", "CF-1") == Conflicted(files=["w.txt"])
