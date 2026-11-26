"""Helpers of the settings tests: a repository folder with `.code-factory/` files, real git."""

import asyncio
import subprocess
from pathlib import Path

GIT_IDENTITY = ["-c", "user.name=t", "-c", "user.email=t@example.com"]


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def git(root: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603
        ["git", *GIT_IDENTITY, *args],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


def repository(root: Path, files: dict[str, str]) -> Path:
    """A git repository on `main` whose files are added to the index (not committed)."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    for name, text in files.items():
        write(root, name, text)
    git(root, "add", "-A")
    return root


async def arepository(root: Path, files: dict[str, str]) -> Path:
    """`repository` in a worker thread: git is a child process and must not block the event loop."""
    return await asyncio.to_thread(repository, root, files)


async def agit(root: Path, *args: str) -> str:
    """`git` in a worker thread."""
    return await asyncio.to_thread(git, root, *args)
