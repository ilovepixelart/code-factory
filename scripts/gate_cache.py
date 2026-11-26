"""Fingerprint the local gate's source and environment. The board always runs with --force."""

import hashlib
import os
import stat
import subprocess
import sys
from pathlib import Path

from gate_delta import git

TOOLCHAIN = (("uv", "--version"), ("node", "--version"), ("pnpm", "--version"))
ENVIRONMENT = ("PATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH")


def fingerprint(base: str) -> str:
    """Hash actual files so staged or unstaged edits invalidate the local pass."""
    files = git(
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
        "--exclude=.claude/worktrees/",
        "--exclude=.code-factory/worktrees/",
    ).stdout
    digest = hashlib.sha256()
    digest.update(git("rev-parse", "--verify", "HEAD").stdout)
    digest.update(base.encode())
    for item in sorted(set(files.split(b"\0")) - {b""}):
        file = Path(os.fsdecode(item))
        digest.update(item + b"\0")
        try:
            mode = file.lstat().st_mode
        except FileNotFoundError:
            digest.update(b"missing\0")
            continue
        if not stat.S_ISREG(mode):
            return ""
        contents = file.read_bytes()
        digest.update(f"{mode}:{len(contents)}:".encode() + contents)
    for tool in TOOLCHAIN:
        version = subprocess.run(  # noqa: S603  # fixed toolchain commands
            tool, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True
        )
        digest.update(version.stdout)
    for name in sorted(os.environ):
        if name in ENVIRONMENT or name.startswith(
            ("PYTEST_", "CODE_FACTORY_TEST_", "CODE_FACTORY_WEB_TEST_")
        ):
            digest.update(f"{name}={os.environ[name]}\0".encode())
    digest.update(sys.version.encode())
    return digest.hexdigest()


def main() -> int:
    """Print a cache key, or no key when this checkout cannot be fingerprinted."""
    try:
        print(fingerprint(sys.argv[1]))
    except OSError, subprocess.CalledProcessError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
