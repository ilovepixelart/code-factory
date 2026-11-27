"""Real git in a temporary directory, and the fake ports the git service is built with."""

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from code_factory.git.adapters.runner import GitRunner
from code_factory.git.models import HookOutcome, PullRef, TicketRef
from code_factory.git.service import GitPorts, GitService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import ConflictError, NotFoundError

ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "LC_ALL": "C",
}  # fmt: skip


def git(cwd: Path, *args: str, check: bool = True) -> str:
    """Run git synchronously for test setup; stdout, stripped."""
    done = subprocess.run(  # noqa: S603  # test setup, fixed program
        ["git", *args],  # noqa: S607
        cwd=cwd,
        env=ENV,
        capture_output=True,
        text=True,
        check=check,
    )
    return done.stdout.strip()


def write(root: Path, name: str, text: str) -> None:
    """Write a file below `root`."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit(root: Path, subject: str, **files: str) -> str:
    """Write files (`a__b` is not special: pass names through `write` for paths) and commit."""
    for name, text in files.items():
        write(root, name.replace("__", "/"), text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", subject)
    return git(root, "rev-parse", "HEAD")


def set_identity(root: Path) -> None:
    """Give Git commands launched by the app a local identity in a test checkout."""
    git(root, "config", "--local", "user.name", ENV["GIT_AUTHOR_NAME"])
    git(root, "config", "--local", "user.email", ENV["GIT_AUTHOR_EMAIL"])


def make_repo(base: Path, name: str = "sample", *, branch: str = "main") -> Path:
    """A checkout with one commit, a bare origin holding it and `origin/HEAD` set."""
    origin = base / f"{name}-origin.git"
    root = base / name
    root.mkdir(parents=True)
    git(base, "init", "-q", "--bare", "-b", branch, str(origin))
    git(root, "init", "-q", "-b", branch)
    set_identity(root)
    git(root, "remote", "add", "origin", str(origin))
    commit(root, "Start", **{"readme.md": "hello\n"})
    git(root, "push", "-q", "origin", branch)
    git(root, "fetch", "-q", "origin")
    git(root, "remote", "set-head", "origin", branch)
    return root


@dataclass
class FakeForge:
    """Records what the service asks of the forge."""

    state: str = "clean"
    opened: list[dict[str, str]] = field(default_factory=list)
    merged: list[str] = field(default_factory=list)

    async def open_pull(self, repository: str, **asked: str) -> PullRef:  # noqa: ARG002
        self.opened.append(asked)
        return PullRef(number=1, url="https://example.test/pull/1")

    async def merge(self, ticket_id: str, ref: PullRef, head: str) -> None:  # noqa: ARG002
        if self.state != "clean":
            raise ConflictError(self.state)
        self.merged.append(head)


@dataclass
class Fakes:
    """One object standing for every port; tests set fields to steer it."""

    roots: dict[str, Path] = field(default_factory=dict)
    tickets: dict[str, TicketRef] = field(default_factory=dict)
    parent: str | None = None
    verdict_: str = "passed"
    checks_configured: bool = False
    held_: str | None = None
    setup: HookOutcome | None = None
    forge: FakeForge = field(default_factory=FakeForge)
    screened: list[tuple[str, str]] = field(default_factory=list)

    async def root_of(self, repository: str) -> Path:
        if repository not in self.roots:
            msg = "unknown repository"
            raise NotFoundError(msg)
        return self.roots[repository]

    async def by_path(self, path: Path) -> str:
        for name, root in self.roots.items():
            if path.is_relative_to(root):
                return name
        msg = f"{path} is not inside a tracked repository"
        raise NotFoundError(msg)

    async def ticket(self, repository: str, ticket_id: str) -> TicketRef:  # noqa: ARG002
        if ticket_id not in self.tickets:
            msg = "no such ticket"
            raise NotFoundError(msg)
        return self.tickets[ticket_id]

    async def record_branch(self, repository: str, ticket_id: str, branch: str) -> None:  # noqa: ARG002
        self.tickets[ticket_id] = self.tickets[ticket_id].model_copy(update={"branch": branch})

    async def stack_parent(self, repository: str, ticket_id: str) -> str | None:  # noqa: ARG002
        return self.parent

    async def verdict(self, repository: str, ticket_id: str, head: str) -> str:  # noqa: ARG002
        return self.verdict_

    async def configured(self, repository: str) -> bool:  # noqa: ARG002
        return self.checks_configured

    async def held(self, repository: str, branch: str, base: str, new: str) -> str | None:  # noqa: ARG002
        self.screened.append((branch, new))
        return self.held_

    async def setup_command(self, repository: str) -> str | None:  # noqa: ARG002
        return None if self.setup is None else "setup"

    async def run_setup(self, repository: str, ticket_id: str, tree: Path) -> HookOutcome:  # noqa: ARG002
        assert self.setup is not None
        return self.setup


def ticket_ref(ticket_id: str = "CF-1", branch: str = "") -> TicketRef:
    """A ticket the fakes can answer with."""
    return TicketRef(
        id=ticket_id, title="A ticket", kind="feature", labels=[], branch=branch, blocker_ids=[]
    )


def make_service(uow: UnitOfWork, fakes: Fakes) -> GitService:
    """A real service over the real runner and the fakes."""
    ports = GitPorts(
        directory=fakes, tickets=fakes, forge=fakes.forge, checks=fakes, screen=fakes, hooks=fakes
    )
    return GitService(uow, GitRunner(()), ports)
