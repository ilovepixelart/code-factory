"""Keeping the checks tidy: lost runs, strays, the supervisor, the keeper, caches and pruning."""

import asyncio
import logging
from collections.abc import Coroutine
from datetime import timedelta
from pathlib import Path
from typing import Any

import anyio
import anyio.to_thread

from code_factory.checks.adapters import cache, main_prefix
from code_factory.checks.models import CacheFolder, CheckRun, PruneReport, RunState
from code_factory.checks.service.base import ACTOR
from code_factory.checks.service.pipeline import PipelineMixin
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.team.models import RunningGate

logger = logging.getLogger(__name__)
STRAY_AGE_S = 300.0
KEEPER_INTERVAL_S = 30.0
FIRST_PASS_S = 1.0
GATE_PREFIX = "gate: "


class UpkeepMixin(PipelineMixin):
    """Supervisor, keeper and maintenance."""

    async def reconcile(self) -> int:
        """Mark runs unbeaten for 60 s lost; remove trees and copies no live run names."""
        now = self._now()
        async with self._db() as store:
            lost = await store.runs.reconcile(now)
            live = await store.runs.active()
        await self._sweep(live, now.timestamp() - STRAY_AGE_S)
        return len(lost)

    async def _sweep(self, live: list[CheckRun], cutoff: float) -> None:
        named = [await anyio.Path(row.workspace).resolve() for row in live if row.workspace]
        keep = frozenset(str(path) for path in (*named, *(path.parent for path in named)))
        for record in await self._deps.repositories.list():
            root = Path(record.path)
            try:
                await self._workspaces.sweep_snapshots(record.name, root, keep, cutoff)
                await self._workspaces.sweep_copies(main_prefix(root), keep, cutoff)
            except Exception:  # one repository's tidy-up never stops the rest
                logger.warning("stray trees of %s could not be removed", record.name, exc_info=True)

    async def tick(self) -> None:
        """One pass of the keeper: reconcile, start due runs, sweep offers and declines."""
        await self.reconcile()
        async with self._db() as store:
            await store.remote.sweep(self._now())
        await self._requeue()
        for record in await self._deps.repositories.list():
            await self._start_due(record.name)

    async def _start_due(self, repository: str) -> None:
        try:
            if await self.due_main(repository) is not None:
                await self.start_main(repository)
        except ConflictError, BadRequestError:
            logger.info("main's run of %s was not started", repository)
        except Exception:  # a repository that cannot be judged never stops the others
            logger.warning("main's run of %s could not be judged", repository, exc_info=True)
        try:
            release = await self.due_verify(repository)
            if release is not None:
                await self._spawn(self.verify(repository, release))
        except Exception:  # the same, for the release verification
            logger.warning("the verification of %s could not be judged", repository, exc_info=True)

    async def _spawn(self, work: Coroutine[Any, Any, object]) -> None:
        """Run `work` in the supervisor's group, or here when there is none."""
        if self._group is None:
            await work
        else:
            self._group.create_task(self._quietly(work))

    @staticmethod
    async def _quietly(work: Coroutine[Any, Any, object]) -> None:
        try:
            await work
        except Exception:
            logger.exception("a check task failed")

    async def _requeue(self) -> None:
        """Queue the rows this process owns that no task has picked up."""
        if self._group is None:
            return
        async with self._db() as store:
            active = await store.runs.active()
        for row in active:
            if row.owner == self._owner and row.state is RunState.QUEUED:
                self._enqueue(row.id)

    async def run_supervisor(self) -> None:
        """Run the checks this process queued, each in a task of its own under the semaphore.

        Rows queued before it ran are picked up by the keeper's next pass.
        """
        async with asyncio.TaskGroup() as group:
            self._group = group
            try:
                while True:
                    check_id = await self._queue.get()
                    group.create_task(self._supervised(check_id), name=f"check-{check_id}")
            finally:
                self._group = None

    async def _supervised(self, check_id: int) -> None:
        try:
            await self.execute(check_id)
        except Exception:
            logger.exception("check %s failed", check_id)

    async def run_keeper(
        self, interval: float = KEEPER_INTERVAL_S, first_pass_after: float = FIRST_PASS_S
    ) -> None:
        """Tick every `interval` seconds, the first after `first_pass_after`.

        A failing pass is logged and the loop goes on.
        """
        await asyncio.sleep(first_pass_after)
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("a pass of the checks keeper failed")
            await asyncio.sleep(interval)

    async def drain(self) -> None:
        """Wait for the running checks for `shutdown_s`, then cancel them."""
        tasks = list(self._running.values())
        if not tasks:
            return
        await asyncio.wait(tasks, timeout=self._opts.shutdown_s)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self, check_id: int) -> None:
        """End the process group of a running check of this process; no record is written."""
        row = await self._row(check_id)
        if row.state not in {RunState.QUEUED, RunState.RUNNING}:
            msg = "the check ended already"
            raise ConflictError(msg)
        if row.owner != self._owner:
            msg = "the check runs in another process"
            raise ConflictError(msg)
        task = self._running.get(check_id)
        if task is None:
            await self._lose(check_id)
        else:
            task.cancel()

    async def attach_flaky(self, ticket_id: str, bug_id: str, by: str) -> str:
        """Record that `bug_id` tracks the failure that makes the latest check flaky; the tree."""
        ticket = await self._ticket(ticket_id)
        bug = await self._deps.tickets.get(bug_id)
        if bug.type != "bug":
            msg = f"{bug_id} is not a bug ticket"
            raise BadRequestError(msg)
        newest = await self._newest_records(ticket.id, 1)
        if not newest:
            msg = f"{ticket_id} has no recorded check"
            raise NotFoundError(msg)
        data = newest[0].data
        tree = str(data.get("tree", ""))
        steps, tests, why = await self._failing_names(
            ticket.repository, ticket.id, str(data.get("log", ""))
        )
        record: dict[str, Any] = {"bug": bug.id, "tree": tree, "steps": steps, "tests": tests}
        if why:
            record["reason"] = why
        await self._deps.tickets.record_activity(ticket.id, "flaky", record, by=by or ACTOR)
        return tree

    async def forget_cache(self, ticket_id: str) -> None:
        """Remove the ticket's build cache after its merge; none is no error."""
        try:
            await anyio.to_thread.run_sync(
                cache.forget, self._opts.state_dir, ticket_id, limiter=cache.CACHE_LIMITER
            )
        except ValueError:
            raise BadRequestError(cache.NAME) from None

    async def cache_folders(self) -> list[CacheFolder]:
        """The ticket caches kept."""
        found = await anyio.to_thread.run_sync(
            cache.folders, self._opts.state_dir, limiter=cache.CACHE_LIMITER
        )
        return [CacheFolder(name=name, path=str(path)) for name, path in found]

    async def prune(self, days: int, *, apply: bool) -> PruneReport:
        """List, or with `apply` remove, the logs and caches older than `days` and old runs."""
        before = self._now() - timedelta(days=days)
        old_logs = await self._logs.older_than(before.timestamp())
        old_caches = [
            folder.name
            for folder in await self.cache_folders()
            if await anyio.to_thread.run_sync(_older, Path(folder.path), before.timestamp())
        ]
        async with self._db() as store:
            runs = await (store.runs.prune(before) if apply else store.runs.prunable(before))
        if apply:
            await self._logs.remove(old_logs)
            for name in old_caches:
                await self.forget_cache(name)
        return PruneReport(logs=[path.name for path in old_logs], caches=old_caches, runs=runs)

    async def running_gates(self) -> list[RunningGate]:
        """The queued and running checks as the team page reads them."""
        async with self._db() as store:
            rows = await store.runs.active()
        lock = await self._heavy.holder()
        gates = []
        for row in rows:
            text = await self._gate_lines(row)
            tree = self._trees.get(row.id) or row.workspace
            gates.append(
                RunningGate(
                    repository=row.repository,
                    ticket_id=row.subject,
                    tree=tree,
                    started_at=(row.started_at or row.queued_at).timestamp(),
                    written_at=row.beat_at.timestamp(),
                    log=text,
                    lock=lock,
                )
            )
        return gates

    async def _gate_lines(self, row: CheckRun) -> str:
        if not row.log_path:
            return ""
        path = await self._logs.within(row.repository, row.subject, row.log_path)
        text = None if path is None else await self._logs.text_of(path)
        lines = [] if text is None else [x for x in text.splitlines() if x.startswith(GATE_PREFIX)]
        return "\n".join(lines)


def _older(path: Path, cutoff: float) -> bool:
    try:
        return path.stat().st_mtime < cutoff
    except OSError:
        return False
