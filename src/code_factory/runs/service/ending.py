"""Ending runs: stop one or all, collect the ones that ended, and run what an end sets off."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from code_factory.agents.service import StartKit
from code_factory.platform.errors import CodeFactoryError, NotFoundError
from code_factory.runs.adapters import files
from code_factory.runs.adapters.processes import Target
from code_factory.runs.models import (
    BUILD_UNVERIFIED_CODE,
    BUILD_UNVERIFIED_REASON,
    STOPPED_CODE,
    TIMEOUT_CODE,
    UNKNOWN_CODE,
    Ended,
    Run,
)
from code_factory.runs.ports import Tree
from code_factory.runs.repository import HaltRepository, RunEnd, RunRepository
from code_factory.runs.rules.budget import limit_until
from code_factory.runs.rules.records import state_of
from code_factory.runs.service.reading import Reading

logger = logging.getLogger(__name__)

UNSPAWNED_AFTER = timedelta(seconds=60)
LOG_WINDOW = 1024 * 1024
NEVER_STARTED = "the run never recorded a process, so the board ended it"


@dataclass(frozen=True)
class _Facts:
    """What the run's log and tree say once it ended."""

    end: RunEnd
    limit: datetime | None


def _tree_of(run: Run) -> Tree:
    path = Path(run.worktree)
    return Tree(name=path.name, path=path, branch=run.branch)


def _target(run: Run, exit_file: Path) -> Target | None:
    if run.pid is None:
        return None
    return Target(run.pid, run.pid_started_at, exit_file)


class Ending(Reading):
    """Stopping, halting and collecting."""

    async def stop(self, run_id: str) -> Run:
        """End a run: SIGTERM its group, SIGKILL after the grace, record the stop.

        An ended run is returned unchanged. Concurrent stops of one run are one.
        """
        return await self._stop(run_id, "")

    async def halt_run(self, run_id: str, reason: str) -> bool:
        """Stop a run and record why; `False` for an unknown or ended run."""
        try:
            before = await self.get(run_id)
        except NotFoundError:
            return False
        if before.exit_code is not None:
            return False
        await self._stop(run_id, reason)
        return True

    async def _stop(self, run_id: str, halted: str) -> Run:
        lock = self._stopping.setdefault(run_id, asyncio.Lock())
        try:
            async with lock:
                current = await self.get(run_id)
                if current.exit_code is not None:
                    return current
                return await self._stopped(current, halted)
        finally:
            self._stopping.pop(run_id, None)

    async def _stopped(self, run: Run, halted: str) -> Run:
        target = _target(run, self.exit_file_of(run))
        if target is not None:
            await self._registry.stop(target)
        redirected = await self._redirection(run)
        facts = await self._facts(run, STOPPED_CODE, halted=redirected or halted)
        ended = await self._end(run, facts)
        if ended is None:
            return await self.get(run.id)
        await self._settle(ended)
        return await self.get(run.id)

    async def _redirection(self, run: Run) -> str:
        """The git sentence when the tree's git folder was redirected; empty when it was not.

        A tree the board no longer records is not a reason to leave a killed agent's row active.
        """
        try:
            return await self._ports.trees.redirection(run.repository, _tree_of(run))
        except CodeFactoryError:
            logger.warning("the tree of run %s could not be checked at its stop", run.id)
            return ""

    async def stop_all(self, by: str) -> list[str]:
        """Hold every agent, then end every active run; the ids of the runs stopped."""
        async with self._uow() as session:
            await HaltRepository(session).halt(by, self._clock())
        try:
            await self.collect()
        except Exception:
            # A run that cannot be collected must not keep the others running.
            logger.exception("the collection before a halt failed")
        async with self._uow() as session:
            active = await RunRepository(session).active()
        await self._end_groups(active)
        stopped: list[str] = []
        for run in active:
            await self._stop(run.id, "")
            stopped.append(run.id)
        return stopped

    async def _end_groups(self, runs: list[Run]) -> None:
        """End every run's process group at once; the records follow one by one."""
        async with asyncio.TaskGroup() as group:
            for run in runs:
                if (target := _target(run, self.exit_file_of(run))) is not None:
                    group.create_task(self._registry.stop(target))

    async def resume(self) -> None:
        """Let agents start again; a second call changes nothing."""
        async with self._uow() as session:
            await HaltRepository(session).resume()

    async def halted_at(self) -> datetime | None:
        """When agents were held, `None` while they may start."""
        async with self._uow() as session:
            halt = await HaltRepository(session).halted()
        return None if halt is None else halt.halted_at

    async def collect(self) -> list[Ended]:
        """One pass: end every run that finished, run the effects of every unsettled end.

        Single flight: a pass started while one runs waits and then finds nothing to do.
        """
        async with self._pass:
            async with self._uow() as session:
                active = await RunRepository(session).active()
            ended: list[Ended] = []
            for run in active:
                result = await self._collect_one(run)
                if result is not None:
                    ended.append(result)
            await self._settle_pending()
            return ended

    async def _settle_pending(self) -> None:
        async with self._uow() as session:
            pending = await RunRepository(session).unsettled()
        for run in pending:
            try:
                await self._settle(run)
            except CodeFactoryError, OSError:
                logger.exception("the end of run %s could not be settled; it is retried", run.id)

    async def _exit_of(self, run: Run) -> int | None:
        """The code a run ended with, or `None` while it still runs."""
        recorded = await files.read_exit(self.exit_file_of(run))
        if recorded is not None:
            return recorded
        target = _target(run, self.exit_file_of(run))
        if target is None:
            young = run.started_at > self._clock() - UNSPAWNED_AFTER
            return None if young else UNKNOWN_CODE
        if await self._registry.alive(target):
            return None
        held = self._registry.returncode(target.pid)
        return UNKNOWN_CODE if held is None else held

    async def _collect_one(self, run: Run) -> Ended | None:
        code = await self._exit_of(run)
        if code is None:
            return None
        halted = NEVER_STARTED if run.pid is None else ""
        if code == TIMEOUT_CODE:
            halted = "the run exceeded its time limit"
        facts = await self._facts(run, code, halted=halted)
        ended = await self._end(run, facts)
        if ended is None:
            return None
        await self._settle(ended)
        return Ended(
            run=await self.get(run.id),
            limit_until=facts.limit,
            stopped=state_of(ended) == "stopped",
        )

    async def _end(self, run: Run, facts: _Facts) -> Run | None:
        async with self._uow() as session:
            return await RunRepository(session).end(run.id, facts.end)

    async def _facts(self, run: Run, code: int, *, halted: str) -> _Facts:
        agents = self._ports.agents
        now = self._clock()
        usage = await agents.log_usage(Path(run.log))
        given = await self._given(run)
        cost, estimated = usage.cost, False
        if cost is None and usage.input_tokens is not None and given is not None:
            price = StartKit.agent_price(given.input_price, given.output_price, local=given.local)
            if price is not None:
                parts = (usage.input_tokens or 0, usage.output_tokens or 0)
                cost, estimated = StartKit.estimate(price, parts), True
        refused = await self._fetched_back(run)  # the commits are read in the main repository
        commits, dirty = await self._tree_facts(run)
        limit = None if code == TIMEOUT_CODE else await self._limit(run, now)
        if code == TIMEOUT_CODE:
            code = STOPPED_CODE
        if (
            code == 0
            and limit is None
            and run.stage == "build"
            and (
                commits is None
                or not commits
                or dirty
                or refused
                or not await self._build_changed(run, commits[-1])
            )
        ):
            code = BUILD_UNVERIFIED_CODE
        return _Facts(
            end=RunEnd(
                exit_code=code,
                ended_at=now,
                cost=cost,
                cost_estimated=estimated,
                tokens=usage.tokens,
                model=usage.model,
                uncommitted=dirty and not bool(commits),
                commits=commits,
                halted=halted or None,
                limited_until=limit,
                looping=False if code == STOPPED_CODE else None,
            ),
            limit=limit,
        )

    async def _build_changed(self, run: Run, head: str) -> bool:
        trees = self._ports.trees
        try:
            before = await trees.tree_id(run.repository, run.head)
            after = await trees.tree_id(run.repository, head)
        except CodeFactoryError:
            logger.warning("the changes of build %s could not be verified", run.id, exc_info=True)
            return False
        return bool(before and after and before != after)

    async def _tree_facts(self, run: Run) -> tuple[list[str] | None, bool]:
        """The commits the run made and whether it left changes; unknown when git cannot say.

        The tree may be redirected, or hold commits the main checkout does not have yet: the run
        still ends, with its commits not recorded.
        """
        trees, tree = self._ports.trees, _tree_of(run)
        try:
            head = await trees.head(tree) if run.head else ""
            commits = (
                []
                if head in {"", run.head}
                else await trees.commits(run.repository, run.head, head)
            )
            return commits, await trees.uncommitted(run.repository, tree)
        except CodeFactoryError:
            logger.warning("the tree of run %s could not be read when it ended", run.id)
            return None, False

    async def _limit(self, run: Run, now: datetime) -> datetime | None:
        text = await files.read_tail(Path(run.log), LOG_WINDOW)
        found = None if text is None else self._ports.agents.usage_limit(text)
        if found is None:
            return None
        settings = await self._ports.config.settings(run.repository)
        until = limit_until(found.reset, now.timestamp(), settings.limit_wait_s)
        return datetime.fromtimestamp(until, UTC)

    async def _settle(self, run: Run) -> None:
        """The effects of an end, each safe to repeat: a crash between them runs them again."""
        ports = self._ports
        target = _target(run, self.exit_file_of(run))
        if target is not None:
            self._registry.end_leftovers(target)
        await ports.tokens.revoke(run.id)
        stopped = state_of(run) == "stopped"
        data: dict[str, object] = {
            "run": run.id,
            "stage": run.stage,
            "exit_code": run.exit_code,
            "commits": run.commits,
            "uncommitted": run.uncommitted,
            "stopped": stopped,
            "tokens": run.tokens,
            "duration_s": None
            if run.ended_at is None
            else (run.ended_at - run.started_at).total_seconds(),
        }
        if run.exit_code == BUILD_UNVERIFIED_CODE:
            data["reason"] = BUILD_UNVERIFIED_REASON
        elif run.halted:
            data["reason"] = run.halted
        await ports.tickets.record_event(run.ticket_key, "run.ended", run.id, data, self._clock())
        refused = await self._fetched_back(run)
        if refused:
            await ports.tickets.record_event(
                run.ticket_key,
                "branch_refused",
                run.id,
                {"run": run.id, "reason": refused},
                self._clock(),
            )
        if run.limited_until is not None:
            until: dict[str, object] = {"run": run.id, "until": run.limited_until.isoformat()}
            await ports.tickets.record_event(
                run.ticket_key, "run.limited", run.id, until, self._clock()
            )
        if stopped:
            await self._snapshot(run)
        else:
            await self._next_step(run, fetched=not refused)
        await files.remove(self.patterns_path(run.id))
        await ports.teams.end_claim(run.ticket_key, run.id)
        async with self._uow() as session:
            await RunRepository(session).settle(run.id, self._clock())

    async def _fetched_back(self, run: Run) -> str:
        """Why the run's branch was not fetched back, empty when it was; repeating it is safe.

        A tree that cannot be read is told as a refusal: it must not keep the run from settling.
        """
        try:
            return await self._ports.trees.fetch_back(run.repository, _tree_of(run))
        except CodeFactoryError as error:
            logger.warning("the branch of run %s could not be fetched back", run.id, exc_info=True)
            return str(error)

    async def _next_step(self, run: Run, *, fetched: bool) -> None:
        """Hand a build's fetched commits to their checks and a review to its verdict.

        A step its owner refuses is logged: the run still settles.
        """
        flow, commits = self._ports.flow, run.commits or []
        try:
            if (
                run.stage == "build"
                and run.attempt == 0
                and commits
                and fetched
                and run.exit_code != BUILD_UNVERIFIED_CODE
            ):
                await flow.build_ended(run.ticket_key, commits[-1])
            elif run.stage == "review":
                await flow.review_ended(run.ticket_key, run.id, run.head)
        except CodeFactoryError as refused:
            logger.warning("the end of run %s set nothing off: %s", run.id, refused)

    async def _snapshot(self, run: Run) -> None:
        try:
            await self._ports.trees.save(run.repository, run.ticket_key, _tree_of(run))
        except CodeFactoryError:
            logger.warning(
                "the unfinished work of run %s could not be saved", run.id, exc_info=True
            )
