"""Fetch back, save and catch up against real git with a bare origin."""

from pathlib import Path

import pytest

from code_factory.git.models import FetchRefusedError, TreeRedirectedError
from code_factory.git.service import GitService
from code_factory.platform.errors import BadRequestError
from git_support import Fakes, commit, git, set_identity, ticket_ref, write


@pytest.fixture
async def clone(service: GitService, root: Path, fakes: Fakes) -> Path:
    fakes.tickets["CF-1"] = ticket_ref(branch="ticket/cf-1")
    await service.start_worktree("sample", "CF-1")
    clone = root / ".code-factory/worktrees/CF-1"
    set_identity(clone)
    return clone


async def test_fetch_back_moves_the_branch_forward_as_a_checked_commit(
    service: GitService, clone: Path, root: Path
) -> None:
    tip = commit(clone, "Clone work", **{"c.txt": "c\n"})
    await service.fetch_back("sample", "CF-1", "ticket/cf-1")
    assert git(root, "rev-parse", "ticket/cf-1") == tip


async def test_fetch_back_refuses_a_branch_that_is_not_forward(
    service: GitService, clone: Path
) -> None:
    commit(clone, "Clone work", **{"c.txt": "c\n"})
    await service.fetch_back("sample", "CF-1", "ticket/cf-1")
    git(clone, "reset", "-q", "--hard", "HEAD~1")
    commit(clone, "Diverged", **{"d.txt": "d\n"})
    with pytest.raises(FetchRefusedError, match="does not build on the branch the board holds"):
        await service.fetch_back("sample", "CF-1", "ticket/cf-1")


async def test_fetch_back_refuses_a_branch_checked_out_in_the_main_checkout(
    service: GitService, clone: Path, root: Path
) -> None:
    git(root, "checkout", "-q", "ticket/cf-1")
    commit(clone, "Clone work", **{"c.txt": "c\n"})
    with pytest.raises(FetchRefusedError, match="checked out in the main repository"):
        await service.fetch_back("sample", "CF-1", "ticket/cf-1")


async def test_fetch_back_refuses_a_missing_branch_and_a_tree_that_fails_validation(
    service: GitService, clone: Path
) -> None:
    with pytest.raises(FetchRefusedError, match="not a commit the board can take"):
        await service.fetch_back("sample", "CF-1", "no-such-branch")
    (clone / ".git/objects/info/alternates").write_text("/x\n")
    with pytest.raises(TreeRedirectedError):
        await service.fetch_back("sample", "CF-1", "ticket/cf-1")


async def test_first_save_second_save_and_an_equal_tree_reuses_the_commit(
    service: GitService, clone: Path
) -> None:
    write(clone, "wip.txt", "one\n")
    first = await service.save_work("sample", "CF-1")
    assert git(clone, "rev-parse", "refs/wip/CF-1") == first.commit
    assert (clone / "wip.txt").exists()  # files and index stay
    assert git(clone, "status", "--porcelain") == "?? wip.txt"
    again = await service.save_work("sample", "CF-1")
    assert again.commit == first.commit
    write(clone, "wip.txt", "two\n")
    second = await service.save_work("sample", "CF-1")
    assert second.commit != first.commit
    assert git(clone, "rev-parse", f"{second.commit}^2") == first.commit  # the ref moves forward


async def test_a_save_leaves_secret_files_out(service: GitService, clone: Path) -> None:
    for name in (".env", "cfg/.env.local", "k.pem", "deep/x.key"):
        write(clone, name, "secret\n")
    write(clone, "ok.txt", "fine\n")
    saved = await service.save_work("sample", "CF-1")
    assert git(clone, "ls-tree", "-r", "--name-only", saved.commit).splitlines() == [
        "ok.txt",
        "readme.md",
    ]


async def test_a_save_pushes_the_wip_ref_and_the_ticket_branch_never_the_default(
    service: GitService, clone: Path, root: Path
) -> None:
    commit(clone, "Committed", **{"c.txt": "c\n"})
    saved = await service.save_work("sample", "CF-1")
    assert saved.sent == ["refs/wip/CF-1", "refs/heads/ticket/cf-1"]
    origin = root.parent / "sample-origin.git"
    assert git(origin, "rev-parse", "refs/wip/CF-1") == saved.commit
    assert git(origin, "rev-parse", "refs/heads/ticket/cf-1") == git(clone, "rev-parse", "HEAD")
    assert git(origin, "rev-parse", "refs/heads/main") == git(root, "rev-parse", "origin/main")


async def test_a_clone_on_another_branch_pushes_only_the_ref(
    service: GitService, clone: Path, root: Path
) -> None:
    git(clone, "checkout", "-q", "-b", "other")
    write(clone, "w.txt", "w\n")
    saved = await service.save_work("sample", "CF-1")
    assert saved.sent == ["refs/wip/CF-1"]
    assert saved.not_sent == ""
    assert git(clone, "rev-parse", "refs/wip/CF-1") == saved.commit
    origin = root.parent / "sample-origin.git"
    assert git(origin, "rev-parse", "refs/wip/CF-1") == saved.commit
    assert git(origin, "rev-parse", "--verify", "-q", "refs/heads/ticket/cf-1", check=False) == ""


async def test_a_save_whose_ticket_branch_is_the_default_pushes_only_the_ref(
    service: GitService, clone: Path, root: Path, fakes: Fakes
) -> None:
    fakes.tickets["CF-1"] = ticket_ref(branch="main")
    git(clone, "checkout", "-q", "-B", "main")
    commit(clone, "Committed on main", **{"c.txt": "c\n"})
    origin = root.parent / "sample-origin.git"
    main_before = git(origin, "rev-parse", "refs/heads/main")
    saved = await service.save_work("sample", "CF-1")
    assert saved.sent == ["refs/wip/CF-1"]
    assert git(origin, "rev-parse", "refs/heads/main") == main_before


async def test_a_secret_held_by_the_screen_pushes_nothing(
    service: GitService, clone: Path, root: Path, fakes: Fakes
) -> None:
    fakes.held_ = "a token in w.txt"
    write(clone, "w.txt", "w\n")
    saved = await service.save_work("sample", "CF-1")
    assert saved.sent == []
    assert saved.not_sent == "the screen held the push: a token in w.txt"
    origin = root.parent / "sample-origin.git"
    assert git(origin, "rev-parse", "--verify", "-q", "refs/wip/CF-1", check=False) == ""


async def test_a_save_of_an_unknown_id_is_refused_and_a_clean_filter_is_refused(
    service: GitService, clone: Path
) -> None:
    with pytest.raises(BadRequestError, match="not a ticket id"):
        await service.save_work("sample", "../x")
    git(clone, "config", "filter.x.clean", "cat")
    write(clone, "w.txt", "w\n")
    with pytest.raises(BadRequestError, match="a filter is set in this tree's git config"):
        await service.save_work("sample", "CF-1")


async def test_catch_up_fast_forwards_a_clean_checkout_and_names_why_it_cannot(
    service: GitService, root: Path
) -> None:
    other = root.parent / "other"
    git(root.parent, "clone", "-q", str(root.parent / "sample-origin.git"), str(other))
    new = commit(other, "Elsewhere", **{"e.txt": "e\n"})
    git(other, "push", "-q", "origin", "main")
    moved = await service.catch_up_main("sample")
    assert moved.moved
    assert git(root, "rev-parse", "HEAD") == new
    git(root, "checkout", "-q", "-b", "side")
    left = await service.catch_up_main("sample")
    assert (left.moved, left.reason) == (False, "it is on side, not main")


async def test_catch_up_refreshes_origin_even_when_the_checkout_is_on_another_branch(
    service: GitService, root: Path
) -> None:
    other = root.parent / "other"
    git(root.parent, "clone", "-q", str(root.parent / "sample-origin.git"), str(other))
    new = commit(other, "Elsewhere", **{"e.txt": "e\n"})
    git(other, "push", "-q", "origin", "main")
    git(root, "checkout", "-q", "-b", "side")
    left = await service.catch_up_main("sample")
    assert (left.moved, left.reason) == (False, "it is on side, not main")
    assert git(root, "rev-parse", "origin/main") == new


async def test_a_hook_of_the_main_checkout_does_not_run_on_a_catch_up(
    service: GitService, root: Path
) -> None:
    other = root.parent / "other"
    git(root.parent, "clone", "-q", str(root.parent / "sample-origin.git"), str(other))
    commit(other, "Elsewhere", **{"e.txt": "e\n"})
    git(other, "push", "-q", "origin", "main")
    marker = root.parent / "post-merge-ran"
    git(root, "config", "core.hooksPath", str(root / ".git/hooks"))  # outranks a global one
    hook = root / ".git/hooks/post-merge"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
    hook.chmod(0o755)
    assert (await service.catch_up_main("sample")).moved
    assert not marker.exists()


async def test_catch_up_names_the_reason_when_a_dirty_file_would_be_overwritten(
    service: GitService, root: Path
) -> None:
    other = root.parent / "other"
    git(root.parent, "clone", "-q", str(root.parent / "sample-origin.git"), str(other))
    commit(other, "Elsewhere", **{"readme.md": "changed upstream\n"})
    git(other, "push", "-q", "origin", "main")
    write(root, "readme.md", "dirty\n")
    result = await service.catch_up_main("sample")
    assert not result.moved
    assert "readme.md" in result.reason or "overwritten" in result.reason
