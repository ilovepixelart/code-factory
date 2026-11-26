"""What git ignores of the env files: secrets are never tracked, a static `.env.<name>` can be."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _ignored(name: str) -> bool:
    result = subprocess.run(  # noqa: S603  # git on a fixed argument list
        ["git", "check-ignore", "--quiet", "--no-index", name],  # noqa: S607
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


@pytest.mark.parametrize("name", [".env", ".env.local", ".env.dev.local"])
def test_git_ignores_the_files_that_may_hold_secrets(name: str) -> None:
    assert _ignored(name)


@pytest.mark.parametrize("name", [".env.example", ".env.dev", ".env.prod"])
def test_git_does_not_ignore_the_files_that_may_be_tracked(name: str) -> None:
    assert not _ignored(name)
