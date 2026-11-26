"""A real temporary git repository with an origin, for the stage adapter tests (no network)."""

import os
import subprocess
from pathlib import Path

IDENTITY = (
    "-c",
    "user.name=Tester",
    "-c",
    "user.email=tester@example.com",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "core.hooksPath=/dev/null",
)
CLEAN = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(root: Path, *args: str) -> str:
    """Run git in `root` and return its output; a failure raises with git's own message."""
    done = subprocess.run(  # noqa: S603  # a fixed program with test-made arguments
        ["git", *IDENTITY, "-C", str(root), *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        env=CLEAN,
    )
    if done.returncode != 0:
        msg = f"git {' '.join(args)} failed: {done.stderr.strip() or done.stdout.strip()}"
        raise RuntimeError(msg)
    return done.stdout.strip()


def commit(root: Path, subject: str, *files: str) -> str:
    """Write each file (its own name as content), commit them with `subject`, answer the commit."""
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{name} {subject}\n")
    git(root, "add", "--all")
    git(root, "commit", "--allow-empty", "-m", subject)
    return git(root, "rev-parse", "HEAD")


def clone_with_origin(base: Path) -> Path:
    """A clone of a fresh bare origin, one commit on `main` pushed; answers the clone's path."""
    origin = base / "origin.git"
    origin.mkdir()
    git(origin, "init", "--bare", "--initial-branch=main")
    work = base / "work"
    git(base, "clone", str(origin), str(work))
    git(work, "checkout", "-b", "main")
    commit(work, "first", "README.md")
    git(work, "push", "--set-upstream", "origin", "main")
    git(work, "remote", "set-head", "origin", "main")
    return work
