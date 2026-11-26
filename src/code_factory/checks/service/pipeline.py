"""Running a queued check: the heartbeat, the snapshot, the kill policy and the conclusion."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from code_factory.checks.adapters import SetupFailedError
from code_factory.checks.models import FIX_CHECK_REQUEST, MAIN, CheckRun, Judged, Ran, Scope
from code_factory.checks.rules import kill_policy
from code_factory.checks.service.command import Attempt, Place
from code_factory.checks.service.config import RunConfig, run_config
from code_factory.checks.service.permit import Permit
from code_factory.checks.service.releasing import ReleasingMixin
from code_factory.platform.errors import CodeFactoryError

logger = logging.getLogger(__name__)
ATTEMPTS = 2


class PipelineMixin(ReleasingMixin):
    """`execute`: one queued row, start to end."""

    async def run_now(self, check_id: int) -> CheckRun:
        """Execute a queued row in the caller: the CLI and tests; the supervisor does the same."""
        return await self.execute(check_id)

    async def execute(self, check_id: int) -> CheckRun:
        """Run the queued check `check_id` here and answer its row.

        A row already ended is answered as it is. A cancelled run is `lost` and writes no record;
        its head is due again.
        """
        async with self._db() as store:
            adopted = await store.runs.adopt(check_id, self._owner, self._now())
        row = await self._row(check_id)
        if not adopted:
            return row
        beat = asyncio.create_task(self._beat(check_id), name=f"check-beat-{check_id}")
        current = asyncio.current_task()
        if current is not None:
            self._running[check_id] = current
        permit = Permit(self._slots)
        self._permits[check_id] = permit
        try:
            await permit.acquire()
            await self._pipeline(row)
        except BaseException:
            await self._lose(check_id)
            raise
        finally:
            beat.cancel()
            await asyncio.gather(beat, return_exceptions=True)
            permit.release()
            self._permits.pop(check_id, None)
            self._running.pop(check_id, None)
            self._known.discard(check_id)
            self._trees.pop(check_id, None)
        return await self._row(check_id)

    async def _beat(self, check_id: int) -> None:
        """Beat the row from its own session until cancelled."""
        while True:
            await asyncio.sleep(self._opts.heartbeat_s)
            try:
                async with self._db() as store:
                    await store.runs.beat(check_id, self._owner, self._now())
            except CodeFactoryError, OSError:
                logger.warning("the heartbeat of check %s failed", check_id, exc_info=True)

    async def _pipeline(self, row: CheckRun) -> None:
        await self._policy.refresh()
        root = await self._root(row.repository)
        config = run_config(await self._deps.settings.load(root))
        if row.subject == MAIN:
            await self._run_main(row, root, config)
        else:
            await self._run_ticket(row, root, config)

    async def _run_ticket(self, row: CheckRun, root: Path, config: RunConfig) -> None:
        runs: list[Ran] = []
        base = time.time_ns()
        for attempt_number in range(ATTEMPTS):
            attempt = await self._attempt(row, root, config, base + attempt_number)
            runs.append(attempt.ran)
            action = kill_policy(runs)
            if not action.rerun:
                extra: dict[str, Any] = {"kills": action.kills} if action.kills else {}
                await self._conclude(row, attempt, extra)
                if (
                    row.scope is Scope.FAST
                    and row.requested_by == FIX_CHECK_REQUEST
                    and attempt.ran.code == 0
                ):
                    await self.queue_head(row.subject, row.commit)
                return
            await self._record(row, attempt, dict(action.record_kill or {}))

    async def _attempt(self, row: CheckRun, root: Path, config: RunConfig, second: int) -> Attempt:
        """One snapshot of the head and one run of the command on it."""
        log = self._logs.path_for(row.repository, row.subject, second)

        async def started(head: str) -> None:
            await self._post_started(row, head)

        try:
            async with self._workspaces.snapshot(
                row.repository, row.commit, row.subject, config.setup
            ) as space:
                self._trees[row.id] = str(space.path)
                place = Place(row, root, config, space.path, space.git_dir, log)
                attempt = await self._attempt_on(place, started)
                space.passed = attempt.ran.code == 0
                return attempt
        except (SetupFailedError, CodeFactoryError) as failed:
            await self._logs.write(log, f"{failed}\n")
            judged = Judged(head=row.commit, tree="", tree_id=row.tree_id)
            return await self._attempt_of(judged, -1, log, slept=False)
