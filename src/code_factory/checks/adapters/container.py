"""The board's checks in a container: the engine's command, the image, what is mounted and how.

The container is named, because killing the `docker run` client leaves its container running: on a
timeout or a cancellation the engine is asked to remove it by name.
"""

import asyncio
import os
import shlex
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import anyio
import anyio.to_thread

from code_factory.agents.service import AgentService, StartKit
from code_factory.checks.adapters.environment import base_environment
from code_factory.checks.adapters.logs import LogFiles
from code_factory.checks.rules import (
    CONTAINER_NOT_STARTED,
    container_name,
    docker_never_started,
    named_container,
)
from code_factory.git.service import GitService
from code_factory.platform.contained import BASE_VARIABLES, OFFLINE
from code_factory.platform.errors import BadRequestError, UnavailableError
from code_factory.platform.process import run_logged, run_process
from code_factory.platform.programs import find_program

DEFAULT_ENGINE = "docker"
NEVER_STARTED = 125
INSPECT_TIMEOUT_S = 30.0
REMOVE_TIMEOUT_S = 15.0
CONTAINER_FILE_BYTES = 1024 * 1024
_files = anyio.CapacityLimiter(2)
Hold = Callable[[], AbstractAsyncContextManager[None]]


class CheckoutDenials(Protocol):
    """What a sandbox denies a tree that is a checkout of its own (`adapters/sandbox.py`)."""

    async def checkout_denials(self, repository: str, tree: Path) -> list[Path]:
        """The paths the board reads outside any sandbox: a container holds them read-only."""
        ...


@dataclass(frozen=True)
class ContainerSpec:
    """The `[checks]` settings that decide a container run."""

    engine: str | None = None
    image: str | None = None
    file: str | None = None
    mounts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContainerRun:
    """One run: what to run, where, and its limits."""

    repository: str
    root: Path
    spec: ContainerSpec
    check_id: int
    command: str
    tree: Path
    log: Path
    limit_s: float | None
    git_dir: Path  # the tree's git folder, read before its setup ran
    checkout: bool = False  # the tree is a repository of its own, not a worktree of the board's


@dataclass(frozen=True)
class _Plan:
    engine: Path
    argv: list[str]
    name: str
    built: list[Path]


def _resolve(path: str) -> str:
    return os.path.realpath(path)


def _git_folders(git_dir: Path, tree: Path) -> list[Path]:
    """The git folders a container mounts read-only: the worktree's and the common one.

    `git_dir` was read before any setup ran in `tree`; the `.git` file inside the tree is the
    checks' to rewrite and is never read here. A git folder inside the tree (a checkout) is
    its own common folder: a `commondir` file planted there is not followed.
    """
    admin = git_dir.resolve()
    common_file = admin / "commondir"
    if admin.is_relative_to(tree.resolve()) or not common_file.is_file():
        return [admin] if admin.is_dir() else []
    common = (admin / common_file.read_text(encoding="utf-8").strip()).resolve()
    return sorted({common, admin})


def _link(path: Path) -> bool:
    return path.is_symlink()


def _prepare_code_factory(tree: Path) -> Path | str:
    """`.code-factory` of `tree`, made first so none is planted; a sentence when it is a link."""
    folder = tree / ".code-factory"
    if _link(folder):
        return f"the checks container cannot hold {folder} read-only: it is a link"
    folder.mkdir(exist_ok=True)
    return folder


def _readonly(tree: Path, git_dir: Path, *, checkout: bool) -> tuple[list[Path], str | None]:
    found = _git_folders(git_dir, tree)
    if checkout:
        folder = _prepare_code_factory(tree)
        if isinstance(folder, str):
            return [], folder
        found.append(folder)
    return sorted(found), None


def _uncovered(denied: Sequence[Path], found: list[Path]) -> list[Path]:
    """The denied folders that exist and lie in none of the folders already mounted."""
    return [p for p in denied if p.exists() and not any(p.is_relative_to(m) for m in found)]


async def _out(work: Callable[..., object], *args: object) -> object:
    return await anyio.to_thread.run_sync(work, *args, limiter=_files)


class ContainerChecks:
    """Runs a checks command in a container of the repository's engine."""

    def __init__(  # noqa: PLR0913  # what a container run reads
        self,
        *,
        agents: AgentService,
        git: GitService,
        logs: LogFiles,
        places: Callable[[], Sequence[Path]],
        state_dir: Path,
        denials: CheckoutDenials,
    ) -> None:
        self._kit: StartKit = agents.kit
        self._git = git
        self._logs = logs
        self._places = places
        self._state = state_dir
        self._denials = denials

    async def run(self, ctx: ContainerRun, hold: Hold) -> int | None:
        """Run the command in the container: `-1` with the reason in the log when it cannot start.

        `hold` is the wait for the container's turn and the heavy-step lock, entered after the
        image is found and left when the run ends; the image is found again after it, because a
        wait can last long enough for the engine to restart and lose it.
        """
        plan = await self._plan(ctx)
        if isinstance(plan, str):
            await self._logs.write(ctx.log, f"{plan}\n")
            return -1
        async with hold():
            again = await self._image(ctx)
            if isinstance(again, str):
                await self._logs.write(ctx.log, f"{again}\n")
                return -1
            plan = _Plan(plan.engine, plan.argv, plan.name, [*plan.built, *again[1]])
            return await self._start(ctx, plan)

    async def _plan(self, ctx: ContainerRun) -> _Plan | str:
        engine_name = ctx.spec.engine or DEFAULT_ENGINE
        engine = await find_program(engine_name, self._places())
        if engine is None:
            return (
                f"the checks container needs {engine_name} on PATH; install it, or remove "
                "[checks] container from .code-factory/config.toml"
            )
        mounts = await self._mounts(ctx)
        if isinstance(mounts, str):
            return mounts
        image = await self._image(ctx, engine)
        if isinstance(image, str):
            return image
        tag, built = image
        readonly = await self._readonly_mounts(ctx)
        if isinstance(readonly, str):
            return readonly
        variables = await self._variables(ctx)
        try:
            words = self._kit.in_container(
                str(engine),
                tag,
                str(ctx.tree),
                readonly=[str(path) for path in readonly],
                mounts=mounts,
                variables=variables,
                command=ctx.command,
            )
        except BadRequestError as refused:
            return str(refused)
        name = container_name(ctx.check_id)
        return _Plan(engine, named_container(words, name), name, built)

    async def _readonly_mounts(self, ctx: ContainerRun) -> list[Path] | str:
        found, problem = await anyio.to_thread.run_sync(
            lambda: _readonly(ctx.tree, ctx.git_dir, checkout=ctx.checkout), limiter=_files
        )
        if problem is not None:
            return problem
        if ctx.checkout:
            denied = await self._denials.checkout_denials(ctx.repository, ctx.tree)
            found += await anyio.to_thread.run_sync(_uncovered, denied, list(found), limiter=_files)
        return found

    async def _variables(self, ctx: ContainerRun) -> list[str]:
        variables = [f"{n}={os.environ[n]}" for n in BASE_VARIABLES if n in os.environ]
        variables.append(OFFLINE)
        base = await self._git.base_tip(ctx.repository)
        if base is not None and base:
            variables.append(f"CODE_FACTORY_CHECKS_BASE={base}")
        return variables

    async def _mounts(self, ctx: ContainerRun) -> list[tuple[str, str]] | str:
        home = Path.home()
        if not home.is_absolute():
            return "the checks container mounts nothing without HOME as an absolute path"
        user = str(await anyio.to_thread.run_sync(_resolve, str(home), limiter=_files))
        state = await anyio.to_thread.run_sync(_resolve, str(self._state), limiter=_files)
        secrets = [self._kit.secret_paths(user)][0]
        resolved = [await anyio.to_thread.run_sync(_resolve, s, limiter=_files) for s in secrets]
        found: list[tuple[str, str]] = []
        for entry in ctx.spec.mounts:
            made = await self._mount(entry, user, state, resolved)
            if isinstance(made, str):
                return made
            found.append(made)
        return found

    async def _mount(
        self, entry: str, user: str, state: str, resolved: list[str]
    ) -> tuple[str, str] | str:
        try:
            host, inside = self._kit.container_mount(entry, user)
        except BadRequestError as refused:
            return str(refused)
        real = await anyio.to_thread.run_sync(_resolve, host, limiter=_files)
        if not await anyio.Path(real).is_dir():
            return f"the checks container cannot mount {host}: no such folder"
        if Path(real).is_relative_to(state) or Path(state).is_relative_to(real):
            return (
                f"the checks container cannot mount {host}, which holds or is in the state folder"
            )
        if self._kit.mount_reaches_secrets(real, user, resolved):
            return (
                f"the checks container cannot mount {host}, which leads to the home folder or a "
                "secret folder"
            )
        return real, inside

    async def _image(
        self, ctx: ContainerRun, engine: Path | None = None
    ) -> tuple[str, list[Path]] | str:
        """The image tag and the build log when it was built just now; a sentence on failure."""
        if ctx.spec.image is not None and ctx.spec.image:
            return ctx.spec.image, []
        named = ctx.spec.file or ""
        refused = f"the checks image did not build from {named}"
        try:
            text = await self._git.read_text_below(ctx.root, named, CONTAINER_FILE_BYTES)
        except BadRequestError:
            return refused
        if text is None:
            return refused
        tag = self._kit.checks_image_tag(text.encode())
        program = engine or await find_program(ctx.spec.engine or DEFAULT_ENGINE, self._places())
        if program is None or await self._holds(program, tag):
            return tag, []
        built = ctx.log.with_suffix(".build.log")
        folder = ctx.root / named
        line = shlex.join(
            [str(program), "build", "--tag", tag, "--file", str(folder), str(folder.parent)]
        )
        code = await run_logged(
            line, cwd=folder.parent, log=built, env=await self._environment(), limit_s=ctx.limit_s
        )
        if code != 0:
            tail = await self._logs.text_of(built) or ""
            return f"{tail}{refused}"
        return tag, [built]

    async def _holds(self, engine: Path, tag: str) -> bool:
        try:
            done = await run_process(
                [str(engine), "image", "inspect", tag],
                env=await self._environment(),
                timeout_s=INSPECT_TIMEOUT_S,
            )
        except UnavailableError:
            return False
        return done.code == 0

    async def _environment(self) -> dict[str, str]:
        return await base_environment(self._places())

    async def _start(self, ctx: ContainerRun, plan: _Plan) -> int | None:
        line = shlex.join(plan.argv)
        for built in reversed(plan.built):
            line = f"/bin/cat {shlex.quote(str(built))}; {line}"
        env = await self._environment()
        try:
            code = await run_logged(line, cwd=ctx.tree, log=ctx.log, env=env, limit_s=ctx.limit_s)
        except asyncio.CancelledError:
            await self._remove(plan, env)
            raise
        if code is None:
            await self._remove(plan, env)
            return None
        if code == NEVER_STARTED:
            text = await self._logs.text_of(ctx.log) or ""
            if docker_never_started(text):
                await self._logs.append(ctx.log, f"\n{CONTAINER_NOT_STARTED}\n")
                return -1
        return code

    async def _remove(self, plan: _Plan, env: dict[str, str]) -> None:
        """Remove the named container: killing its client leaves it running."""
        with anyio.CancelScope(shield=True):
            try:
                await run_process(
                    [str(plan.engine), "rm", "-f", plan.name], env=env, timeout_s=REMOVE_TIMEOUT_S
                )
            except UnavailableError:
                return
