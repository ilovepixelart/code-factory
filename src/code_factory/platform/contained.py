"""Run a command on code a run wrote, inside srt (the sandbox runtime) or as it is.

When the repository keeps the sandbox off the command runs as it is. Checks, worktree hooks, the
board's git in a run's clone and previews all go through `ContainedRunner.run`.

Sandboxed, the line is `env -i <base variables> CLAUDE_CODE_TMPDIR=<tmp> XDG_RUNTIME_DIR=<tmp>
[CODE_FACTORY_OFFLINE=1] <srt> --settings <file> -c <command>`, every word quoted: srt gets only the
base environment, a settings file in the state folder (which the work cannot reach) and a
temporary folder of its own, all removed afterwards. Without srt, or when the settings cannot be
made, nothing runs: the log says why and the code is -1.

What this file does not decide comes through two ports: `ContainedPolicy` (is the sandbox on, the
repository's `.nvmrc`, the folders a run may write) and `SandboxSettings` (the srt rules).
"""

import os
import shlex
import shutil
import tempfile
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import anyio
import anyio.to_thread

from code_factory.platform.errors import UnavailableError
from code_factory.platform.process import run_logged
from code_factory.platform.programs import (
    find_path,
    find_pinned_node,
    find_program,
)

ENV_PROGRAM = "/usr/bin/env"  # by its path, with only the base variables
OFFLINE = "CODE_FACTORY_OFFLINE=1"  # tells a contained checks run it reaches no host
BASE_VARIABLES = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TMPDIR",
    "TERM",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
)
SANDBOX_PROGRAM = "srt"
# PATH when no folder is trusted: an empty PATH, or an empty entry in it, means the current folder.
EMPTY_PATH = "/var/empty"
_files = anyio.CapacityLimiter(4)


class Work(StrEnum):
    """What runs contained; it decides the settings, the offline flag and the sentence."""

    CHECKS = "checks"
    SETUP = "setup"
    TEARDOWN = "teardown"
    GIT = "git"
    PREVIEW = "preview"

    @property
    def folder(self) -> str:
        """The state subfolder its settings file goes in."""
        return "checks" if self is Work.CHECKS else "hooks"

    @property
    def subject(self) -> str:
        """What could not run, for the sentence a missing srt leaves in the log."""
        return {
            Work.CHECKS: "the checks run",
            Work.SETUP: "the worktree hooks run",
            Work.TEARDOWN: "the worktree hooks run",
            Work.GIT: "the board's git in a run's clone runs",
            Work.PREVIEW: "the preview runs",
        }[self]


class ContainedPolicy(Protocol):
    """What the repository's configuration decides."""

    async def sandboxed(self, repository: str) -> bool:
        """Whether `[agents] sandbox` is on."""

    async def nvmrc(self, repository: str) -> str | None:
        """The text of the main checkout's `.nvmrc`, read below the root, or None."""

    def places(self) -> Sequence[Path]:
        """The folders a run may write (see `programs`)."""


class SandboxSettings(Protocol):
    """The srt settings JSON for one run.

    Each method raises `UnavailableError(sentence)` when the settings cannot be made.
    """

    async def tree_settings(
        self, repository: str, tree: Path, log: Path, temporary: Path, *, reaches_hosts: bool
    ) -> str:
        """Checks and worktree hooks; only a setup reaches the package hosts."""

    async def git_settings(self, repository: str, tree: Path, log: Path, temporary: Path) -> str:
        """The board's git in a run's clone."""

    async def preview_settings(
        self, repository: str, tree: Path, log: Path, temporary: Path
    ) -> str:
        """A live preview of a ticket's worktree."""


def missing_sandbox(subject: str) -> str:
    """The sentence a log holds when srt is not installed."""
    return (
        f"{subject} inside srt (@anthropic-ai/sandbox-runtime), which is not installed; install "
        "it, or set [agents] sandbox = false in .code-factory/config.toml"
    )


def _make_scratch() -> Path:
    # srt hands every command `/tmp/claude` as its temp folder unless told another.
    return Path(tempfile.mkdtemp(prefix="code-factory-tmp-")).resolve()


def _write_settings(folder: Path, text: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(suffix=".sandbox.json", dir=folder)
    with os.fdopen(handle, "w") as settings:
        settings.write(text)
    return Path(name)


def _write_refusal(log: Path, reason: str) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(f"{reason}\n")


def _remove(scratch: Path | None, settings: Path | None) -> None:
    if scratch is not None:
        shutil.rmtree(scratch, ignore_errors=True)
    if settings is not None:
        settings.unlink(missing_ok=True)


class ContainedRunner:
    """Runs one command contained as its `Work` says. Callers bound how many run at once."""

    def __init__(
        self,
        *,
        policy: ContainedPolicy,
        sandbox: SandboxSettings,
        state_dir: Path,
        program: str = SANDBOX_PROGRAM,
    ) -> None:
        self._policy = policy
        self._sandbox = sandbox
        self._state_dir = state_dir
        self._program = program

    async def run(  # noqa: PLR0913, PLR0917  # what one contained run is
        self,
        work: Work,
        repository: str,
        command: str,
        tree: Path,
        log: Path,
        limit_s: float | None,
        *,
        require_sandbox: bool = False,
    ) -> int | None:
        """Run `command` in `tree`, its output in `log`.

        The exit code; None past `limit_s`; -1 when it could not be contained (the log says why).
        Only a preview may run without a limit. The command sees the base variables and `PATH`,
        sandboxed or not, so a check never reads the board's database URL or tokens.
        """
        if limit_s is None and work is not Work.PREVIEW:
            msg = f"a {work.value} run needs a time limit"
            raise ValueError(msg)
        places = self._policy.places()
        pinned = await find_pinned_node(await self._policy.nvmrc(repository), places)
        path = await find_path(places) or EMPTY_PATH
        env = {**_base_values(), "PATH": path}
        if not await self._policy.sandboxed(repository):
            if require_sandbox:
                msg = "the spec checks require the agent sandbox; enable it and retry Build"
                raise UnavailableError(msg)
            line = command if pinned is None else _pinned(pinned, command)
            return await run_logged(line, cwd=tree, log=log, env=env, limit_s=limit_s)
        scratch = await anyio.to_thread.run_sync(_make_scratch, limiter=_files)
        settings: Path | None = None
        try:
            made = await self._srt_line(
                work=work,
                repository=repository,
                command=command,
                places=(tree, log, scratch),
                pinned=pinned,
            )
            if isinstance(made, str):
                await anyio.to_thread.run_sync(_write_refusal, log, made, limiter=_files)
                return -1
            line, settings = made
            return await run_logged(line, cwd=tree, log=log, env=env, limit_s=limit_s)
        finally:
            await anyio.to_thread.run_sync(_remove, scratch, settings, limiter=_files)

    async def _rules(
        self, work: Work, repository: str, places: tuple[Path, Path, Path]
    ) -> str | UnavailableError:
        tree, log, scratch = places
        try:
            if work is Work.GIT:
                return await self._sandbox.git_settings(repository, tree, log, scratch)
            if work is Work.PREVIEW:
                return await self._sandbox.preview_settings(repository, tree, log, scratch)
            return await self._sandbox.tree_settings(
                repository, tree, log, scratch, reaches_hosts=work is Work.SETUP
            )
        except UnavailableError as refused:
            return refused

    async def _srt_line(
        self,
        *,
        work: Work,
        repository: str,
        command: str,
        places: tuple[Path, Path, Path],
        pinned: Path | None,
    ) -> tuple[str, Path] | str:
        """The line and its settings file, or the sentence that says why it cannot be made."""
        rules = await self._rules(work, repository, places)
        if isinstance(rules, UnavailableError):
            return str(rules)
        srt = await find_program(self._program, self._policy.places(), pinned=pinned)
        if srt is None:
            return missing_sandbox(work.subject)
        environment = await self._base_environment(pinned)
        folder = self._state_dir / work.folder
        try:
            settings = await anyio.to_thread.run_sync(
                _write_settings, folder, rules, limiter=_files
            )
        except OSError as error:
            return f"the sandbox settings cannot be written in {folder}: {error.strerror}"
        scratch = places[2]
        words = [
            ENV_PROGRAM,
            "-i",
            *environment,
            f"CLAUDE_CODE_TMPDIR={scratch}",
            f"XDG_RUNTIME_DIR={scratch}",
            *([OFFLINE] if work is Work.CHECKS else []),
            str(srt),
            "--settings",
            str(settings),
            "-c",
            command,
        ]
        return " ".join(shlex.quote(word) for word in words), settings

    async def _base_environment(self, pinned: Path | None) -> list[str]:
        path = await find_path(self._policy.places(), pinned=pinned) or EMPTY_PATH
        values = {**_base_values(), "PATH": path}
        return [f"{name}={value}" for name, value in values.items()]


def _base_values() -> dict[str, str]:
    return {name: os.environ[name] for name in BASE_VARIABLES if name in os.environ}


def _pinned(folder: Path, command: str) -> str:
    return f'PATH={shlex.quote(str(folder))}:"$PATH"; export PATH; {command}'
