"""One attempt of the checks command on a tree: judge it, wait for its turn, run it, judge again."""

import asyncio
import os
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from code_factory.checks.adapters import ContainerRun, base_environment
from code_factory.checks.models import CheckRun, Containment, Judged, Ran
from code_factory.checks.rules import (
    CONTAINER_WAIT,
    MOVED,
    board_text,
    checks_limit,
    judged_exit,
    phases_line,
    phases_of,
    slept_between,
    timing_line,
    wait_bound,
)
from code_factory.checks.service.base import CheckBase
from code_factory.checks.service.config import RunConfig
from code_factory.platform.contained import Work
from code_factory.platform.errors import UnavailableError
from code_factory.stages.models import LogReading

HEAVY_WAIT_VARIABLE = "CODE_FACTORY_HEAVY_WAIT"
SETUP_CHANGED = "gate: the snapshot's setup changed tracked files: no verdict"
NOT_STARTED = -1  # what a run that could not be contained, or ran out of time, exits


@dataclass(frozen=True)
class Place:
    """What one attempt runs on: the row, the checkout, its settings, the tree and the log."""

    row: CheckRun
    root: Path
    config: RunConfig
    tree: Path
    git_dir: Path
    log: Path
    checkout: bool = False  # the tree is a repository of its own, not a worktree of the board's
    turn: bool = True  # wait for the container's turn: not a search run, whose row already holds it


@dataclass
class Timing:
    """Where the time of one attempt went."""

    began: float = field(default_factory=time.monotonic)
    waited: float = 0.0
    started: float | None = None


@dataclass(frozen=True)
class Attempt:
    """What one attempt came to: the judged tree, how it ended and what its log says."""

    judged: Judged
    ran: Ran
    log: Path
    slept: bool
    text: str | None
    reading: LogReading | None


def limit_seconds(timeout: int | None) -> float | None:
    """The limit of a run in seconds, `None` for no limit."""
    limit = checks_limit(timeout)
    return None if limit is None else limit.total_seconds()


class CommandMixin(CheckBase):
    """Running the checks command on a tree, plain, in srt or in a container."""

    async def _judge(self, place: Place) -> Judged:
        """The commit checked out in the tree, the name of its state and its tree id."""
        return (await self._judge_state(place))[0]

    async def _judge_state(self, place: Place) -> tuple[Judged, bool]:
        """What `_judge` says and whether no tracked file differs from the commit.

        A tree that cannot be read raises `UnavailableError`: it is no verdict.
        """
        env = await base_environment(self._policy.places())
        state = await self._judge_tree.read(place.git_dir, place.tree, env)
        tree_id = await self._deps.git.tree_id(place.row.repository, state.head)
        judged = Judged(head=state.head, tree=state.name, tree_id=tree_id, tracked=state.tracked)
        return judged, state.tracked_clean

    async def _note(self, check_id: int, **values: object) -> None:
        async with self._db() as store:
            await store.runs.note(check_id, values)

    async def _turn(self, check_id: int, slots: int, log: Path) -> None:
        """Wait for the container's turn: the oldest queued container run when a slot is free."""
        await self._note(
            check_id, contained=Containment.CONTAINER.value
        )  # the turn counts rows by it
        if await self._granted(check_id, slots):
            return
        await self._logs.write(log, f"{CONTAINER_WAIT}\n")
        waiting = self._wait_for_turn(check_id, slots)
        permit = self._permits.get(check_id)
        if permit is None:
            await waiting
        else:
            await permit.without(waiting)

    async def _granted(self, check_id: int, slots: int) -> bool:
        async with self._db() as store:
            return await store.runs.take_turn(check_id, slots, self._now())

    async def _wait_for_turn(self, check_id: int, slots: int) -> None:
        while True:
            await asyncio.sleep(self._opts.turn_poll_s)
            if await self._granted(check_id, slots):
                return

    def _hold(
        self, place: Place, timing: Timing, started: Callable[[], Awaitable[None]] | None
    ) -> Callable[[], AbstractAsyncContextManager[None]]:
        """The container's turn and the heavy-step lock, held while its command runs."""

        async def say(what: str) -> None:
            await self._logs.append(place.log, f"gate: checks {what}\n")

        @asynccontextmanager
        async def hold() -> AsyncGenerator[None]:
            waiting = time.monotonic()
            if place.turn:
                await self._turn(place.row.id, place.config.slots, place.log)
            bound = wait_bound(os.environ.get(HEAVY_WAIT_VARIABLE))
            lock = await self._heavy.take(board_text(os.getpid(), str(place.tree)), bound, say)
            timing.waited = time.monotonic() - waiting
            try:
                if started is not None:
                    await started()
                yield
            finally:
                await self._cleanup(lock.release())

        return hold

    async def _run_command(
        self, place: Place, started: Callable[[], Awaitable[None]] | None, timing: Timing
    ) -> int | None:
        """Run the command, contained as the repository asks.

        None when it ran out of time; -1 when it could not be started (the log says why).
        """
        row, config = place.row, place.config
        limit = limit_seconds(config.timeout)
        command = config.command(row.scope)
        if config.containment() is Containment.CONTAINER:
            ctx = ContainerRun(
                repository=row.repository,
                root=place.root,
                spec=config.spec,
                check_id=row.id,
                command=command,
                tree=place.tree,
                log=place.log,
                limit_s=limit,
                git_dir=place.git_dir,
                checkout=place.checkout,
            )
            code = await self._containers.run(ctx, self._hold(place, timing, started))
        else:
            await self._begin(row.id)
            if started is not None:
                await started()
            code = await self._runner.run(
                Work.CHECKS, row.repository, command, place.tree, place.log, limit
            )
        return code

    async def _begin(self, check_id: int) -> None:
        async with self._db() as store:
            await store.runs.start(check_id, self._now(), {})

    async def _attempt_on(
        self, place: Place, started: Callable[[str], Awaitable[None]] | None = None
    ) -> Attempt:
        """Judge the tree, run the command and judge it again; the log gets the closing lines."""
        row, log = place.row, place.log
        timing = Timing()
        before, clean = await self._judge_state(place)
        await self._note(row.id, workspace=str(place.tree), log_path=str(log))
        if not clean:
            await self._logs.append(log, f"{SETUP_CHANGED}\n")
            return await self._attempt_of(before, NOT_STARTED, log, slept=False)
        asleep = await self._opts.sleep_time()

        async def begun() -> None:
            timing.started = time.monotonic()
            if started is not None:
                await started(before.head)

        ended = await self._run_command(place, begun, timing)
        started_command = ended != NOT_STARTED
        code = NOT_STARTED if ended is None else ended
        after = await self._judge_after(place, before)
        code, moved = judged_exit(before, after, code)
        if moved:
            await self._logs.append(log, f"\n{MOVED}\n")
        woke = await self._opts.sleep_time() if code != 0 else None
        if timing.started is not None and started_command:
            await self._close_log(log, before.head, timing)
        return await self._attempt_of(before, code, log, slept_between(asleep, woke, code))

    async def _judge_after(self, place: Place, before: Judged) -> Judged:
        """The tree again; one that cannot be read any more reads as another tree."""
        try:
            return await self._judge(place)
        except UnavailableError:
            return before.model_copy(update={"tree": ""})

    async def _close_log(self, log: Path, head: str, timing: Timing) -> None:
        """The timing and phases lines a finished command adds to its log."""
        now = time.monotonic()
        total = now - timing.began
        command = now - (timing.started or now)
        setup = max(total - timing.waited - command, 0.0)
        text = await self._logs.text_of(log) or ""
        lines = [
            timing_line(total, timing.waited, setup, command),
            phases_line(head, timing.waited, phases_of(text)),
        ]
        await self._logs.append(log, "\n" + "\n".join(lines) + "\n")

    async def _attempt_of(self, judged: Judged, code: int, log: Path, slept: bool) -> Attempt:
        """The attempt as the kill policy and the record read it."""
        stages = self._deps.stages
        text = await self._logs.text_of(log)
        ran = Ran(code=code, log=str(log), killed=False)
        reading = None
        if text is not None:
            reading = stages.read_log(text, code)
            if stages.killed_run(code, text):
                ran = ran.model_copy(
                    update={"killed": True, "step": stages.last_started_step(text)}
                )
        return Attempt(judged=judged, ran=ran, log=log, slept=slept, text=text, reading=reading)
