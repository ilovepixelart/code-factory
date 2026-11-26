"""What the `demo` sample writes outside the database: git repositories and agent transcripts.

The board reads git and the agents' hooks for its facts, so the demo gives it real ones: each
repository is a clone of a bare `origin` with a back-dated history, and a session is recorded by
running the board's own capture hook on the payload an agent runtime sends.
"""

import asyncio
import json
import os
import shlex
import struct
import zlib
from collections.abc import Mapping, Sequence
from pathlib import Path

import anyio
import anyio.to_thread

from code_factory.platform.errors import UnavailableError
from code_factory.platform.process import run_process

DAY_S = 86_400
AUTHOR = ("Demo Builder", "builder@demo.invalid")
FORGE = "acme"
HOOK_TIMEOUT_S = 10.0


class DemoGit:
    """A demo repository: a working clone at `root/<name>` of a bare `root/origin/<name>.git`."""

    def __init__(self, root: Path, name: str, now: float) -> None:
        self.path = root / name
        self._origin = root / "origin" / f"{name}.git"
        self._now = now

    async def _git(self, *args: str, at: float | None = None, cwd: Path | None = None) -> str:
        when = f"@{int(at if at is not None else self._now)} +0000"
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": AUTHOR[0],
            "GIT_AUTHOR_EMAIL": AUTHOR[1],
            "GIT_COMMITTER_NAME": AUTHOR[0],
            "GIT_COMMITTER_EMAIL": AUTHOR[1],
            "GIT_AUTHOR_DATE": when,
            "GIT_COMMITTER_DATE": when,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        result = await run_process(["git", *args], cwd=cwd or self.path, env=env)
        if result.code != 0:
            msg = f"git {' '.join(args)} failed in {cwd or self.path}: {result.stderr.decode()}"
            raise UnavailableError(msg)
        return result.stdout.decode().strip()

    def _days_ago(self, days: float) -> float:
        return self._now - days * DAY_S

    async def create(self, files: Mapping[str, str], days_ago: float) -> None:
        """The origin and the clone, with one commit of `files` on `main`, pushed."""
        await anyio.Path(self._origin.parent).mkdir(parents=True, exist_ok=True)
        await self._git(
            "init", "--bare", "--initial-branch=main", str(self._origin), cwd=self._origin.parent
        )
        await self._git("clone", str(self._origin), str(self.path), cwd=self._origin.parent)
        await self._commit(files, "Start the project", self._days_ago(days_ago))
        await self._git("push", "origin", "main")

    async def _commit(self, files: Mapping[str, str], message: str, at: float) -> None:
        await anyio.to_thread.run_sync(_write_files, self.path, files)
        await self._git("add", "--", *files)
        await self._git("commit", "-m", message, at=at)

    async def branch(self, branch: str, change: str, title: str, days_ago: float) -> str:
        """A branch off `main` with one commit adding `change`; its head."""
        await self._git("switch", "-c", branch, "main")
        text = f"# {title}\n"
        await self._commit({change: text}, title, self._days_ago(days_ago))
        head = await self._git("rev-parse", "HEAD")
        await self._git("switch", "main")
        return head

    async def push(self, branch: str) -> None:
        """Push `branch` to origin."""
        await self._git("push", "origin", branch)

    async def tree(self, commit: str) -> str:
        """The id of the tree `commit` records."""
        return await self._git("rev-parse", f"{commit}^{{tree}}")

    async def worktree(self, name: str, branch: str) -> Path:
        """A worktree of `branch` where the board keeps a run's trees; its path."""
        tree = self.path / ".code-factory" / "worktrees" / name
        await self._git("worktree", "add", str(tree), branch)
        return tree

    async def merge(self, branch: str, pull: int, days_ago: float) -> None:
        """Merge `branch` into `main` as the forge merges pull request `pull`, and push."""
        message = f"Merge pull request #{pull} from {FORGE}/{branch}"
        await self._git("merge", "--no-ff", "-m", message, branch, at=self._days_ago(days_ago))
        await self._git("push", "origin", "main", branch)


async def run_hook(command: str, payload: Mapping[str, object]) -> None:
    """Run a hook command as an agent runtime does: the payload on standard input."""
    process = await asyncio.create_subprocess_exec(
        *shlex.split(command),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    async with asyncio.timeout(HOOK_TIMEOUT_S):
        await process.communicate(json.dumps(payload).encode())


def write_transcript(path: Path, records: Sequence[Mapping[str, object]]) -> None:
    """A transcript as the agent runtime writes it: one JSON record a line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def write_png(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    """A plain PNG of one colour, for a capture."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    row = b"\x00" + bytes(rgb) * width
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
    png += chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _write_files(root: Path, files: Mapping[str, str]) -> None:
    """Write `files` under `root`, making their folders; run on a worker thread."""
    for name, text in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
