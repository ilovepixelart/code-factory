"""The tree a screenshot set is recorded against: git's own tree id of the ref."""

import subprocess
from pathlib import Path

import pytest

from code_factory.platform.errors import BadRequestError
from code_factory.screens.adapters import tree_of


def _git(root: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603  # git on a fixture repository
        ["git", "-C", str(root), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text("a\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "a")
    return tmp_path


async def test_the_tree_of_a_ref_is_the_one_git_names(repository: Path) -> None:
    assert await tree_of(repository, "HEAD") == _git(repository, "rev-parse", "HEAD^{tree}")


async def test_a_ref_that_names_no_commit_is_refused_with_the_ref_and_folder(
    repository: Path,
) -> None:
    with pytest.raises(BadRequestError) as refused:
        await tree_of(repository, "no-such-branch")

    assert str(refused.value) == f"no-such-branch names no commit in {repository}"
