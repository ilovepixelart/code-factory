"""Helpers of the checks tests: a movable clock, a fake forge and sandbox, real git branches."""

import os
import stat
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from code_factory.checks.models import PullHead
from code_factory.platform.errors import UnavailableError
from git_support import commit, git

START = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
REPO = "sample"


class Clock:
    """A clock that moves only when a test says so."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def after(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@dataclass
class FakeForge:
    """Records the statuses posted and answers the open pull requests' heads."""

    posts: list[tuple[str, str, str, str, str]] = field(default_factory=list)
    heads: list[PullHead] = field(default_factory=list)
    fail: bool = False

    async def post_commit_status(
        self, repository: str, commit: str, state: str, context: str, description: str
    ) -> bool:
        if self.fail:
            msg = "the forge is down"
            raise UnavailableError(msg)
        self.posts.append((repository, commit, state, context, description))
        return True

    async def open_pull_heads(self, repository: str) -> list[PullHead]:
        return [head for head in self.heads if head.repository == repository]

    def states(self) -> list[str]:
        return [post[2] for post in self.posts]


@dataclass
class FakeSandbox:
    """The srt settings port: records each call and answers a fixed JSON, or refuses."""

    refuse: str | None = None
    calls: list[str] = field(default_factory=list)

    async def _settings(self, kind: str) -> str:
        self.calls.append(kind)
        if self.refuse is not None:
            raise UnavailableError(self.refuse)
        return '{"kind": "' + kind + '"}'

    async def tree_settings(self, *_: object, **__: object) -> str:
        return await self._settings("tree")

    async def git_settings(self, *_: object, **__: object) -> str:
        return await self._settings("git")

    async def preview_settings(self, *_: object, **__: object) -> str:
        return await self._settings("preview")

    async def checkout_denials(self, repository: str, tree: Path) -> list[Path]:  # noqa: ARG002
        return []


def write_config(root: Path, text: str) -> None:
    """Write `.code-factory/config.toml` of the checkout."""
    folder = root / ".code-factory"
    folder.mkdir(exist_ok=True)
    (folder / "config.toml").write_text(text, encoding="utf-8")


def branch_with(root: Path, branch: str, subject: str = "Work", **files: str) -> str:
    """A branch off main with one commit; the checkout goes back to main. The commit id."""
    git(root, "checkout", "-q", "-b", branch)
    made = commit(root, subject, **files)
    git(root, "checkout", "-q", "main")
    return made


def script(path: Path, body: str) -> Path:
    """An executable shell script, the stand-in for a program the board starts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def reachable(pid: int) -> bool:
    """Whether the process exists (a signal of 0); only for a pid above 1 a test started."""
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


ENGINE_SCRIPT = """\
OUT={out}
case "$1" in
  image) echo "$@" >> $OUT/inspect; [ -e $OUT/image_present ]; exit $? ;;
  build) echo "$@" >> $OUT/build; echo "step 1/1 building"; exit 0 ;;
  rm) echo "$@" >> $OUT/rm; exit 0 ;;
  run)
    printf '%s\\n' "$@" > $OUT/run_argv
    echo started > $OUT/started
    case "$(cat $OUT/mode 2>/dev/null)" in
      sleep) echo $$ > $OUT/pid; sleep 30; exit 0 ;;
      killonce) if [ -e $OUT/killed ]; then exit 0; else touch $OUT/killed; kill -9 $$; fi ;;
      daemon) echo "docker: Error response from daemon: boom" >&2; exit 125 ;;
      late) echo "gate: preflight starts"
            echo "docker: Error response from daemon: late" >&2; exit 125 ;;
      *) exit 0 ;;
    esac ;;
esac
"""


def container_config(engine: Path, *extra: str, image: str = "img:1", timeout: int = 60) -> str:
    return (
        "[checks]\ncommand = 'true'\n"
        f"container = '{image}'\ncontainer_engine = '{engine}'\ntimeout = {timeout}\n"
        + "\n".join(extra)
        + "\n"
    )
