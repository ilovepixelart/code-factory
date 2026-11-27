"""Main's own checks: a run on each new tip of the default branch, and the search for the merge."""

import logging
from pathlib import Path
from typing import Any

from code_factory.checks.adapters import SetupFailedError
from code_factory.checks.models import (
    MAIN,
    CheckRun,
    MainFailure,
    MainRecord,
    Scope,
)
from code_factory.checks.rules import (
    Bisection,
    blame_ticket,
    cause_before_any_step,
    complete_main,
    failed_step,
    first_parent_merges,
    log_tail,
    main_due,
    slept_between,
    ticket_ids,
)
from code_factory.checks.service.command import Place, Timing
from code_factory.checks.service.concluding import verdict_of
from code_factory.checks.service.config import RunConfig
from code_factory.checks.service.remote import RemoteMixin
from code_factory.platform.errors import BadRequestError, CodeFactoryError, ConflictError

logger = logging.getLogger(__name__)
SHORT = 7
NO_TIP = "the repository has no default branch tip to check"


class _SleptError(Exception):
    """The machine slept through a failing run of the search."""


class MainMixin(RemoteMixin):
    """Due runs of `[checks] main`, their records and their blame."""

    async def main_records(self) -> list[MainRecord]:
        """Every repository's latest run on its default branch."""
        async with self._db() as store:
            return await store.records.all_main()

    async def due_main(self, repository: str) -> str | None:
        """The tip a run of `[checks] main` is due on, or None.

        None while a check of a ticket runs in the repository, a main run is queued, or a remote
        runner is taking main's run.
        """
        if (await self._config(repository)).commands[Scope.FULL] is None:
            return None
        tip = await self._deps.git.base_tip(repository)
        if tip is None:
            return None
        async with self._db() as store:
            recorded = await store.records.main(repository)
            active = await store.runs.active(repository)
        if active or not main_due(recorded, tip):
            return None
        return None if await self.main_left_to_runners(repository, tip) else tip

    async def start_main(self, repository: str, tip: str | None = None) -> int:
        """Queue a run of `[checks] main` on `tip` (the default branch's by default)."""
        config = await self._config(repository)
        config.command(Scope.FULL)
        commit = tip or await self._deps.git.base_tip(repository)
        if commit is None or not commit:
            raise BadRequestError(NO_TIP)
        row = await self._insert(
            repository, MAIN, commit, (Scope.FULL, config.containment(), "board")
        )
        if row is None:
            msg = "main's run is already queued"
            raise ConflictError(msg)
        self._wake.set()
        return row.id

    async def blame_ticket(self, repository: str, merge: str) -> str:
        """The ticket a merge brought in: its branch's id, else its second parent's subject."""
        git = self._deps.git
        subject = await git.subject(repository, merge) or ""
        branch = git.merged_branch(subject) or ""
        second = await git.subject(repository, f"{merge}^2") or ""
        known = set()
        for candidate in ticket_ids(branch):
            try:
                known.add((await self._deps.tickets.get(candidate)).id)
            except CodeFactoryError:
                continue
        return blame_ticket(branch, second, known)

    async def failing_default_branches(self) -> list[MainFailure]:
        """The failing runs on default branches, with the log's tail and the ticket to blame."""
        failures = []
        for record in await self.main_records():
            if not record.failed:
                continue
            path = await self._logs.within(record.repository, MAIN, record.log)
            text = None if path is None else await self._logs.text_of(path)
            ticket = ""
            if record.broken_by:
                ticket = await self.blame_ticket(record.repository, record.broken_by)
            failures.append(
                MainFailure(
                    repository=record.repository,
                    commit=record.commit,
                    step=record.step,
                    reason=record.reason,
                    exit_code=record.exit_code,
                    log=record.log,
                    tail="" if text is None else log_tail(text),
                    passed=record.passed,
                    broken_by=record.broken_by,
                    ticket=ticket,
                    at=record.at,
                )
            )
        return failures

    async def _run_main(self, row: CheckRun, root: Path, config: RunConfig) -> None:
        """Run `[checks] main` on a copy of the tip and record it; search for a merge on a break."""
        log = self._logs.path_for(row.repository, MAIN, int(self._now().timestamp()))
        in_setup = False
        asleep = False
        try:
            async with self._workspaces.main_copy(
                row.repository, root, row.commit, log, config.setup
            ) as space:
                place = Place(row, root, config, space.path, space.git_dir, log, checkout=True)
                attempt = await self._attempt_on(place)
            code, asleep = attempt.ran.code, attempt.slept
            text, reading = attempt.text or "", attempt.reading
        except (SetupFailedError, CodeFactoryError) as failed:
            in_setup = isinstance(failed, SetupFailedError)
            code, text, reading = -1, f"{failed}\n", None
            if not in_setup:
                await self._logs.write(log, text)
        if asleep:
            await self._lose(row.id)
            return
        done = await self._keep_main(row, log, (code, text, reading), in_setup=in_setup)
        if done.failed and done.exit_code > 0 and done.passed and not done.searched:
            await self._search(row, root, config, done)
        await self._end_main(row, done)

    async def _keep_main(
        self, row: CheckRun, log: Path, outcome: tuple[int, str, Any], *, in_setup: bool
    ) -> MainRecord:
        """Complete the run with the record before it and keep it."""
        code, text, reading = outcome
        run = MainRecord(
            repository=row.repository,
            commit=row.commit,
            exit_code=code,
            log=str(log),
            at=self._now(),
        )
        step = ""
        if code != 0:
            named = failed_step(reading.reported_steps) if reading is not None else ""
            step = "setup" if in_setup else named or cause_before_any_step(text)
        async with self._db() as store:
            previous = await store.records.main(row.repository)
            done = complete_main(
                previous,
                run,
                step=step,
                reason=reading.failure_reason if reading is not None else "",
            )
            await store.records.put_main(done)
        return done

    async def _end_main(self, row: CheckRun, done: MainRecord) -> None:
        code = done.exit_code
        async with self._db() as store:
            await store.runs.finish(
                row.id,
                self._now(),
                verdict_of(code, no_verdict=self._deps.stages.no_verdict(code)),
                {"exit_code": code, "log_path": done.log},
            )

    async def _search(self, row: CheckRun, root: Path, config: RunConfig, done: MainRecord) -> None:
        """Find the first merge since the last pass on which main's command fails, by bisection.

        A search a sleep cut short leaves the record unsearched, so the tip is due again.
        """
        git = self._deps.git
        found: str | None = None
        if await git.is_ancestor(row.repository, done.passed, done.commit):
            entries = await git.read_new_commits(row.repository, done.passed, done.commit)
            merges = first_parent_merges({e.commit: e.parents for e in entries}, done.commit)
            steps = Bisection(len(merges), last_fails=merges[-1:] == [done.commit])
            outcome: bool | None = False
            try:
                while (index := steps.next_index()) is not None:
                    outcome = await self._try_merge(row, root, config, done, merges[index])
                    if outcome is None:
                        break
                    steps.answer(failed=outcome)
            except _SleptError:
                return
            found = None if steps.found is None or outcome is None else merges[steps.found]
        async with self._db() as store:
            await store.records.put_main(
                done.model_copy(update={"broken_by": found or "", "searched": True})
            )

    async def _try_merge(
        self, row: CheckRun, root: Path, config: RunConfig, done: MainRecord, merge: str
    ) -> bool | None:
        """Whether main's command fails on `merge`; None when the search must stop."""
        stem = Path(done.log).stem
        log = Path(done.log).with_name(f"{stem}-search-{merge[:SHORT]}.log")
        try:
            asleep = await self._opts.sleep_time()
            async with self._workspaces.main_copy(
                row.repository, root, merge, log, config.setup
            ) as space:
                place = Place(
                    row, root, config, space.path, space.git_dir, log, checkout=True, turn=False
                )
                ran = await self._run_command(place, None, Timing())
                code = -1 if ran is None else ran
            woke = await self._opts.sleep_time() if code != 0 else None
        except CodeFactoryError:
            logger.warning("the search for the merge that broke main ended", exc_info=True)
            return None
        if slept_between(asleep, woke, code):
            raise _SleptError
        if code < 0:
            logger.warning("the run on %s did not start or was ended", merge[:SHORT])
            return None
        return code != 0
