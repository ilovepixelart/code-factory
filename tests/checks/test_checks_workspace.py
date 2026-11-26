"""Snapshots and main copies made by real git, and the judge that reads them."""

import math
import tempfile
from pathlib import Path

import pytest

from checks_support import REPO, FakeSandbox
from code_factory.checks.adapters import Setup, SetupFailedError, TreeJudge, Workspaces, main_prefix
from code_factory.git.service import GitService
from code_factory.platform.contained import ContainedRunner
from git_support import git

TREES = ".code-factory/worktrees"


class PlainPolicy:
    """No sandbox, no pinned node; a run may write `/tmp`."""

    def __init__(self, root: Path) -> None:
        self._root = root

    async def sandboxed(self, repository: str) -> bool:  # noqa: ARG002
        return False

    async def nvmrc(self, repository: str) -> str | None:  # noqa: ARG002
        return None

    def places(self) -> list[Path]:
        return [self._root, Path("/tmp"), Path("/var/tmp")]  # noqa: S108


@pytest.fixture
def workspaces(git_service: GitService, root: Path, state: Path) -> Workspaces:
    runner = ContainedRunner(policy=PlainPolicy(root), sandbox=FakeSandbox(), state_dir=state)
    return Workspaces(git_service, runner, state)


@pytest.fixture
def judge(root: Path) -> TreeJudge:
    return TreeJudge(lambda: [root, Path("/tmp"), Path("/var/tmp")])  # noqa: S108


async def test_a_snapshot_is_a_detached_worktree_of_the_commit_among_the_boards_trees(
    workspaces: Workspaces, root: Path
) -> None:
    head = git(root, "rev-parse", "HEAD")
    async with workspaces.snapshot(REPO, head, "CF-1", None) as space:
        assert space.path.parent == root.resolve() / TREES or space.path.parent == root / TREES
        assert space.path.name.startswith("check-")
        assert git(space.path, "rev-parse", "HEAD") == head
        assert (space.path / "readme.md").read_text() == "hello\n"
        assert space.git_dir.parent.name == "worktrees"
    assert not space.path.exists()
    assert "check-" not in git(root, "worktree", "list")


async def test_a_snapshot_is_removed_when_the_block_raises(
    workspaces: Workspaces, root: Path
) -> None:
    head = git(root, "rev-parse", "HEAD")
    holder: list[Path] = []

    async def block() -> None:
        async with workspaces.snapshot(REPO, head, "CF-1", None) as space:
            holder.append(space.path)
            msg = "stop"
            raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="stop"):
        await block()
    assert not holder[0].exists()


async def test_a_setup_that_fails_removes_the_snapshot_and_names_its_log(
    workspaces: Workspaces, root: Path, state: Path
) -> None:
    head = git(root, "rev-parse", "HEAD")
    snapshot = workspaces.snapshot(REPO, head, "CF-1", Setup("exit 7", 30))
    with pytest.raises(
        SetupFailedError, match=r"^the snapshot's setup failed with exit code 7; see "
    ):
        async with snapshot:
            pytest.fail("the block must not run")
    assert not list((root / TREES).glob("check-*"))
    assert any((state / "checks").glob("check-*.setup.log"))


async def test_the_setup_runs_in_the_tree_with_the_pnpm_store_named(
    workspaces: Workspaces, root: Path
) -> None:
    head = git(root, "rev-parse", "HEAD")
    setup = Setup('pwd > setup-ran.txt; echo "$pnpm_config_store_dir" >> setup-ran.txt', 30)
    async with workspaces.snapshot(REPO, head, "CF-1", setup) as space:
        lines = (space.path / "setup-ran.txt").read_text().splitlines()
    assert Path(lines[0]).resolve() == space.path.resolve()
    assert lines[1] == str(space.path / "target" / "pnpm-store")


async def test_a_main_copy_is_a_repository_of_its_own_removed_after(
    workspaces: Workspaces, root: Path, tmp_path: Path
) -> None:
    head = git(root, "rev-parse", "HEAD")
    log = tmp_path / "main.log"
    async with workspaces.main_copy(REPO, root, head, log, None) as space:
        assert (space.path / ".git").is_dir()
        assert git(space.path, "rev-parse", "HEAD") == head
        assert space.path.name == "tree"
        scratch = space.path.parent
        assert scratch.name.startswith("code-factory-main-")
    assert not scratch.exists()


async def test_the_judge_names_the_commit_and_a_state_that_changes_with_the_files(
    workspaces: Workspaces, judge: TreeJudge, root: Path
) -> None:
    head = git(root, "rev-parse", "HEAD")
    async with workspaces.snapshot(REPO, head, "CF-1", None) as space:
        clean = await judge.read(space.git_dir, space.path, {})
        again = await judge.read(space.git_dir, space.path, {})
        (space.path / "readme.md").write_text("changed\n")
        edited = await judge.read(space.git_dir, space.path, {})
        (space.path / "new.txt").write_text("untracked\n")
        added = await judge.read(space.git_dir, space.path, {})
    assert clean.head == head
    assert again == clean
    assert len({clean.name, edited.name, added.name}) == 3
    assert edited.head == added.head == head


async def test_a_git_file_rewritten_to_point_elsewhere_does_not_hide_a_change(
    workspaces: Workspaces, judge: TreeJudge, root: Path, tmp_path: Path
) -> None:
    head = git(root, "rev-parse", "HEAD")
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    git(decoy, "init", "-q", "-b", "main")
    async with workspaces.snapshot(REPO, head, "CF-1", None) as space:
        before = await judge.read(space.git_dir, space.path, {})
        (space.path / "readme.md").write_text("changed\n")
        (space.path / ".git").write_text(f"gitdir: {decoy / '.git'}\n")
        after = await judge.read(space.git_dir, space.path, {})
    assert after.head == head
    assert after.name != before.name


async def test_a_sweep_leaves_the_snapshot_a_run_is_using_and_removes_a_stray_one(
    workspaces: Workspaces, git_service: GitService, root: Path
) -> None:
    head = git(root, "rev-parse", "HEAD")
    stray = await git_service.add_snapshot(REPO, head)
    async with workspaces.snapshot(REPO, head, "CF-1", None) as space:
        removed = await workspaces.sweep_snapshots(REPO, root, frozenset(), math.inf)
        assert [Path(r).resolve() for r in removed] == [stray.resolve()]
        assert space.path.is_dir()
    assert not space.path.exists()


async def test_a_sweep_leaves_the_copy_a_run_is_using_and_removes_a_stray_one(
    workspaces: Workspaces, root: Path, tmp_path: Path
) -> None:
    head = git(root, "rev-parse", "HEAD")
    prefix = main_prefix(root)
    async with workspaces.main_copy(REPO, root, head, tmp_path / "main.log", None) as space:
        stray = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
        removed = await workspaces.sweep_copies(prefix, frozenset(), math.inf)
        assert [Path(r).resolve() for r in removed] == [stray.resolve()]
        assert space.path.is_dir()
    assert not space.path.exists()
