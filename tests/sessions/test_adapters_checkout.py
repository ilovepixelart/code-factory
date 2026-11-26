import shutil
import subprocess
from pathlib import Path

import pytest

from code_factory.sessions.adapters import CheckoutLocator
from code_factory.sessions.models import Checkout

GIT = shutil.which("git") or "git"


def git(folder: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603  # a fixed program with fixed words
        [
            GIT,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=folder,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    """A repository `sample` on main with one commit."""
    root = tmp_path / "sample"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "a.txt").write_text("a")
    git(root, "add", "a.txt")
    git(root, "commit", "-q", "-m", "first")
    return root


async def test_a_repository_and_its_branch_come_from_a_folder_inside_it(sample: Path) -> None:
    (sample / "sub").mkdir()
    locator = CheckoutLocator()
    assert await locator.locate(str(sample)) == Checkout("sample", "main")
    assert await locator.locate(str(sample / "sub")) == Checkout("sample", "main")


async def test_a_linked_worktree_belongs_to_its_main_checkout_on_its_own_branch(
    sample: Path,
) -> None:
    tree = sample.parent / "sample-wt"
    git(sample, "worktree", "add", "-q", "-b", "feat/CF-2", str(tree))
    assert await CheckoutLocator().locate(str(tree)) == Checkout("sample", "feat/CF-2")


async def test_a_detached_head_shows_the_first_eight_characters_of_the_revision(
    sample: Path,
) -> None:
    tree = sample.parent / "sample-detached"
    git(sample, "worktree", "add", "-q", "--detach", str(tree))
    revision = git(tree, "rev-parse", "HEAD")
    assert await CheckoutLocator().locate(str(tree)) == Checkout("sample", revision[:8])


async def test_a_board_run_tree_belongs_to_the_checkout_that_made_it(sample: Path) -> None:
    tree = sample / ".code-factory" / "worktrees" / "CF-2"
    tree.mkdir(parents=True)
    git(tree, "init", "-q", "-b", "ticket/cf-2")
    assert await CheckoutLocator().locate(str(tree)) == Checkout("sample", "ticket/cf-2")


@pytest.mark.parametrize("name", ["missing", "", "nowhere/place"])
async def test_a_folder_in_no_repository_or_a_missing_one_is_none_not_an_error(
    tmp_path: Path, name: str
) -> None:
    cwd = "" if name == "" else str(tmp_path / name)
    assert await CheckoutLocator().locate(cwd) is None


async def test_a_changed_branch_is_seen_once_the_cache_time_has_passed(sample: Path) -> None:
    clock = [100.0]
    locator = CheckoutLocator(ttl=5.0, monotonic=lambda: clock[0])
    assert await locator.locate(str(sample)) == Checkout("sample", "main")
    git(sample, "checkout", "-q", "-b", "other")
    clock[0] = 104.9
    assert await locator.locate(str(sample)) == Checkout("sample", "main")
    clock[0] = 105.1
    assert await locator.locate(str(sample)) == Checkout("sample", "other")


async def test_expire_drops_only_answers_past_their_time(sample: Path) -> None:
    clock = [0.0]
    locator = CheckoutLocator(ttl=5.0, monotonic=lambda: clock[0])
    await locator.locate(str(sample))
    git(sample, "checkout", "-q", "-b", "later")
    locator.expire()
    assert await locator.locate(str(sample)) == Checkout("sample", "main")
    clock[0] = 6.0
    locator.expire()
    assert await locator.locate(str(sample)) == Checkout("sample", "later")


async def test_a_pointer_file_that_is_no_gitdir_gives_no_branch(tmp_path: Path) -> None:
    folder = tmp_path / "odd"
    folder.mkdir()
    (folder / ".git").write_text("something else")
    assert await CheckoutLocator().locate(str(folder)) == Checkout("odd", "")
