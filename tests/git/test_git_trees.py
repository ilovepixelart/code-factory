"""Run clones and hand worktrees: start, validation against planted redirects, removal."""

from pathlib import Path

import anyio
import pytest

from code_factory.git.models import HookOutcome, TreeKind, TreeRedirectedError
from code_factory.git.service import GitService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnavailableError,
)
from git_support import Fakes, commit, git, make_repo, ticket_ref, write


def tree_of(root: Path, name: str = "CF-1") -> Path:
    return root / ".code-factory/worktrees" / name


async def test_start_cuts_a_clone_from_origin_default_records_the_branch_and_the_row(
    service: GitService, root: Path, fakes: Fakes
) -> None:
    info = await service.start_worktree("sample", "CF-1")
    tree = tree_of(root)
    assert (info.kind, info.branch, info.path) == (TreeKind.CLONE, "ticket/cf-1", str(tree))
    assert git(tree, "rev-parse", "--abbrev-ref", "HEAD") == "ticket/cf-1"
    assert git(tree, "config", "--get", "branch.ticket/cf-1.remote", check=False) == ""
    assert git(tree, "rev-parse", "HEAD") == git(root, "rev-parse", "origin/main")
    assert fakes.tickets["CF-1"].branch == "ticket/cf-1"
    assert (await service.list_trees("sample"))[0].name == "CF-1"
    assert ".code-factory/worktrees/" in (root / ".git/info/exclude").read_text()
    assert (await service.validate_tree("sample", "CF-1")).is_clone


async def test_start_again_returns_the_same_tree(service: GitService) -> None:
    first = await service.start_worktree("sample", "CF-1")
    again = await service.start_worktree("sample", "CF-1")
    assert again == first.model_copy(update={"made": False})


async def test_only_the_start_that_makes_the_tree_says_it_made_it(service: GitService) -> None:
    first = await service.start_worktree("sample", "CF-1")
    again = await service.start_worktree("sample", "CF-1")
    assert (first.made, again.made) == (True, False)


async def test_a_stacked_ticket_is_cut_from_its_parents_branch(
    service: GitService, root: Path, fakes: Fakes
) -> None:
    git(root, "checkout", "-q", "-b", "ticket/cf-9")
    parent_tip = commit(root, "Parent work", **{"p.txt": "p\n"})
    git(root, "checkout", "-q", "main")
    fakes.parent = "ticket/cf-9"
    await service.start_worktree("sample", "CF-1")
    assert git(tree_of(root), "rev-parse", "HEAD") == parent_tip


async def test_an_attempt_is_cut_from_the_ticket_branch_when_it_exists(
    service: GitService, root: Path, fakes: Fakes
) -> None:
    git(root, "checkout", "-q", "-b", "ticket/cf-1")
    tip = commit(root, "Work", **{"w.txt": "w\n"})
    git(root, "checkout", "-q", "main")
    fakes.tickets["CF-1"] = ticket_ref(branch="ticket/cf-1")
    info = await service.start_worktree("sample", "CF-1", attempt=2)
    assert (info.name, info.branch) == ("CF-1-2", "ticket/cf-1-attempt-2")
    assert git(tree_of(root, "CF-1-2"), "rev-parse", "HEAD") == tip


async def test_a_repository_with_no_commits_is_refused(
    tmp_path: Path, uow: UnitOfWork, fakes: Fakes
) -> None:
    from git_support import make_service  # noqa: PLC0415

    empty = tmp_path / "empty"
    empty.mkdir()
    git(empty, "init", "-q", "-b", "main")
    fakes.roots["empty"] = empty
    with pytest.raises(BadRequestError, match="no commits yet"):
        await make_service(uow, fakes).start_worktree("empty", "CF-1")


async def test_a_repository_with_no_info_folder_still_gets_the_exclude_line(
    tmp_path: Path,
    uow: UnitOfWork,
    fakes: Fakes,
) -> None:
    from git_support import make_service  # noqa: PLC0415

    root = make_repo(tmp_path, "bare-info")
    import shutil  # noqa: PLC0415

    shutil.rmtree(root / ".git/info")
    fakes.roots["bare-info"] = root
    await make_service(uow, fakes).start_worktree("bare-info", "CF-1")
    assert ".code-factory/worktrees/" in (root / ".git/info/exclude").read_text()


async def test_a_failed_setup_removes_the_tree_and_the_row(
    service: GitService, root: Path, fakes: Fakes
) -> None:
    fakes.setup = HookOutcome(code=3, log=root / "setup.log")
    with pytest.raises(UnavailableError, match="setup failed with exit code 3; see"):
        await service.start_worktree("sample", "CF-1")
    assert not tree_of(root).exists()
    assert await service.list_trees("sample") == []
    fakes.setup = HookOutcome(code=None)
    with pytest.raises(UnavailableError, match="did not finish in time"):
        await service.start_worktree("sample", "CF-1")


async def test_a_by_hand_worktree_is_linked_and_a_run_start_refuses_it(
    service: GitService, root: Path
) -> None:
    info = await service.start_worktree("sample", "CF-1", owner_by_hand=True)
    assert info.kind is TreeKind.WORKTREE
    assert "gitdir:" in (tree_of(root) / ".git").read_text()
    assert (await service.validate_tree("sample", "CF-1")).is_clone is False
    with pytest.raises(ConflictError, match="linked worktree of the main repository"):
        await service.start_worktree("sample", "CF-1")


async def test_protected_paths_are_four_for_a_clone_and_seven_for_a_worktree(
    service: GitService, fakes: Fakes
) -> None:
    fakes.tickets["CF-2"] = ticket_ref("CF-2")
    await service.start_worktree("sample", "CF-1")
    await service.start_worktree("sample", "CF-2", owner_by_hand=True)
    assert len(await service.protected_paths("sample", "CF-1")) == 4
    assert len(await service.protected_paths("sample", "CF-2")) == 7


@pytest.fixture
async def clone(service: GitService, root: Path) -> Path:
    await service.start_worktree("sample", "CF-1")
    return tree_of(root)


async def refused(service: GitService) -> None:
    with pytest.raises(TreeRedirectedError):
        await service.validate_tree("sample", "CF-1")


async def test_a_planted_alternates_file_is_refused(service: GitService, clone: Path) -> None:
    (clone / ".git/objects/info/alternates").write_text("/somewhere/objects\n")
    await refused(service)


async def test_a_planted_commondir_is_refused(service: GitService, clone: Path) -> None:
    (clone / ".git/commondir").write_text("../elsewhere\n")
    await refused(service)


async def test_a_swapped_token_is_refused(service: GitService, clone: Path) -> None:
    (clone / ".git/code-factory-clone").write_text("f" * 32 + "\n")
    await refused(service)


async def test_a_git_folder_replaced_by_a_link_is_refused(
    service: GitService, clone: Path, root: Path
) -> None:
    import shutil  # noqa: PLC0415

    shutil.rmtree(clone / ".git")
    (clone / ".git").symlink_to(root / ".git")
    await refused(service)


async def test_a_nested_git_folder_is_refused_for_a_path_inside_the_tree(
    service: GitService, clone: Path
) -> None:
    (clone / "sub").mkdir()
    git(clone / "sub", "init", "-q")
    with pytest.raises(TreeRedirectedError):
        await service.head_of(clone / "sub")


@pytest.mark.usefixtures("clone")
async def test_a_clone_without_its_row_is_never_trusted(
    service: GitService,
    uow: UnitOfWork,
) -> None:
    from code_factory.git.repository import GitStore  # noqa: PLC0415

    async with uow() as session:
        await GitStore(session).remove_tree("sample", "CF-1")
    with pytest.raises(NotFoundError):
        await service.validate_tree("sample", "CF-1")
    listed = await service.list_trees("sample")
    assert [(t.name, t.valid) for t in listed] == [("CF-1", False)]


async def test_a_by_hand_start_over_a_folder_with_no_row_refuses_and_keeps_the_folder(
    service: GitService, root: Path
) -> None:
    folder = tree_of(root)
    folder.mkdir(parents=True)
    (folder / "precious.txt").write_text("mine\n")
    with pytest.raises(ConflictError, match=r"CF-1 .*no record"):
        await service.start_worktree("sample", "CF-1", owner_by_hand=True)
    assert (folder / "precious.txt").read_text() == "mine\n"


async def test_a_run_start_over_a_planted_repository_runs_none_of_its_commands(
    service: GitService, root: Path, fakes: Fakes
) -> None:
    fakes.tickets["CF-2"] = ticket_ref("CF-2")
    folder = tree_of(root, "CF-2")
    folder.mkdir(parents=True)
    git(folder, "init", "-q")
    marker = root.parent / "smudge-ran"
    git(folder, "config", "filter.x.smudge", f"touch {marker}; cat")
    (folder / ".git/info/attributes").write_text("* filter=x\n")
    with pytest.raises(ConflictError, match="no record"):
        await service.start_worktree("sample", "CF-2")
    assert not marker.exists()
    assert (folder / ".git").is_dir()


async def test_an_fsmonitor_in_a_clone_does_not_run_under_the_boards_git(
    service: GitService, clone: Path
) -> None:
    git(clone, "config", "core.fsmonitor", f"touch {clone}/fsmonitor-ran")
    await service.tree_name(clone)
    assert not (clone / "fsmonitor-ran").exists()


async def test_remove_tree_trashes_then_deletes_and_drops_the_row(
    service: GitService, clone: Path, root: Path
) -> None:
    await service.remove_tree("sample", "CF-1")
    assert not await anyio.Path(clone).exists()
    assert await service.list_trees("sample") == []
    assert list((root / ".git/code-factory-trash").iterdir()) == []


async def test_empty_trash_deletes_what_a_stop_left(service: GitService, root: Path) -> None:
    trash = root / ".git/code-factory-trash/CF-9.abc"
    write(trash, "x/y.txt", "left\n")
    assert await service.empty_trash("sample") == []
    assert not trash.exists()


@pytest.mark.usefixtures("clone")
async def test_a_tree_reached_through_a_link_or_outside_the_folder_is_refused(
    service: GitService,
    root: Path,
    tmp_path: Path,
    uow: UnitOfWork,
) -> None:
    from code_factory.git.models import TreeRecord  # noqa: PLC0415
    from code_factory.git.repository import GitStore  # noqa: PLC0415

    outside = tmp_path / "outside"
    outside.mkdir()
    write(outside, "keep.txt", "k\n")
    record = TreeRecord(
        repository="sample",
        name="CF-7",
        kind=TreeKind.CLONE,
        ticket_id="CF-7",
        attempt=0,
        branch="b",
        path=str(outside),
        token="a" * 32,
    )
    async with uow() as session:
        await GitStore(session).add_tree(record)
    with pytest.raises(ConflictError, match="is not directly in"):
        await service.remove_tree("sample", "CF-7")
    assert (outside / "keep.txt").exists()
    link = root / ".code-factory/worktrees/CF-8"
    link.symlink_to(outside)
    await service.remove_tree("sample", "CF-8")
    assert not link.is_symlink()
    assert (outside / "keep.txt").exists()  # the link was removed, never followed


async def test_reconcile_drops_rows_of_gone_folders_and_names_unrecorded_ones(
    service: GitService, clone: Path, root: Path
) -> None:
    (root / ".code-factory/worktrees/stray").mkdir()
    import shutil  # noqa: PLC0415

    shutil.rmtree(clone)
    assert await service.reconcile_trees("sample") == ["stray"]
    assert [t.name for t in await service.list_trees("sample")] == ["stray"]
