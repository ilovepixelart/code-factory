"""What a finished attempt leaves: the ticket's record, a flaky bug, a commit status, the row."""

import logging
from typing import Any

from code_factory.checks.models import CHECKS_CONTEXT, CheckRun, Scope, Verdict
from code_factory.checks.rules import checks_record, status_for
from code_factory.checks.service.base import ACTOR
from code_factory.checks.service.command import Attempt, CommandMixin
from code_factory.platform.errors import CodeFactoryError, ConflictError
from code_factory.tickets.models import NewTicket

logger = logging.getLogger(__name__)
RUNNING_DESCRIPTION = "The board's checks are running"
FLAKY_EXPECTED = "Expected: the checks give the same result on the same tree every time."


def verdict_of(code: int, *, no_verdict: bool) -> Verdict:
    """The verdict a finished row holds."""
    if code == 0:
        return Verdict.PASSED
    return Verdict.NO_VERDICT if no_verdict else Verdict.FAILED


class ConcludeMixin(CommandMixin):
    """Records, flaky tracking, commit statuses and the end of a row."""

    async def _record(
        self, row: CheckRun, attempt: Attempt, extra: dict[str, Any]
    ) -> dict[str, Any]:
        """Append the attempt's `checks` record to the ticket; the record's data."""
        data = checks_record(
            attempt.judged,
            attempt.ran.code,
            attempt.ran.log,
            attempt.reading,
            slept=attempt.slept,
            text=attempt.text,
            extra={**extra, **({} if row.scope is Scope.REACHED else {"scope": row.scope.value})},
        )
        try:
            await self._deps.tickets.record_activity(row.subject, "checks", data, by=ACTOR)
        except CodeFactoryError:
            logger.warning(
                "the checks record of %s could not be written", row.subject, exc_info=True
            )
        return data

    async def _post(self, repository: str, state: str, commit: str, description: str) -> None:
        try:
            await self._deps.forge.post_commit_status(
                repository, commit, state, CHECKS_CONTEXT, description
            )
        except Exception:
            logger.warning("the checks status of %s could not be posted", commit, exc_info=True)

    async def _post_final(self, repository: str, data: dict[str, Any]) -> None:
        status = status_for(data)
        if status is not None:
            await self._post(repository, status[0], str(data["commit"]), status[1])

    async def _post_started(self, row: CheckRun, head: str) -> None:
        """Publish pending when the command starts, while the commit is still the open head."""
        if row.scope is Scope.FAST:
            return
        try:
            heads = await self._deps.forge.open_pull_heads(row.repository)
        except Exception:
            logger.warning(
                "the open pull requests of %s could not be read", row.repository, exc_info=True
            )
            return
        if any(pull.ticket_id == row.subject and pull.head == head for pull in heads):
            await self._post(row.repository, "pending", head, RUNNING_DESCRIPTION)

    async def _failing_names(
        self, repository: str, ticket: str, named: str
    ) -> tuple[list[str], list[str], str]:
        """The steps, tests and reason a failing log says: from the log the record names."""
        path = await self._logs.within(repository, ticket, named)
        text = None if path is None else await self._logs.text_of(path)
        if text is None:
            return [], [], ""
        reading = self._deps.stages.read_log(text)
        steps = reading.flaky_steps or [
            s for s, state in reading.reported_steps if state == "failed"
        ]
        return steps, reading.failing_tests, reading.failure_reason

    async def _file_flaky(self, repository: str, ticket: str, tree: str) -> None:
        """After a pass on `tree`: file the bug of a failure there that nothing excuses."""
        try:
            await self._file(repository, ticket, tree)
        except CodeFactoryError:
            logger.warning("the flaky check of %s could not be tracked", ticket, exc_info=True)

    async def _file(self, repository: str, ticket: str, tree: str) -> None:
        reading = await self._deps.stages.flaky(ticket, tree)
        if reading is None:
            return
        title = f"A check of {ticket} failed on tree {tree[:7]} before it passed"
        new = NewTicket(
            repository=repository,
            title=title,
            type="bug",
            labels=["gate", "flaky"],
            priority="medium",
            source=f"flaky:{ticket}:{tree}",
            description=f"{reading.reason} {FLAKY_EXPECTED}",
        )
        tickets = self._deps.tickets
        try:
            bug = (await tickets.create(new, by=ACTOR)).id
        except ConflictError:
            found = await tickets.find_by_source(repository, new.source or "")
            if found is None:
                raise
            bug = found.id
        await self._attach((repository, ticket), bug, tree, (reading.log, reading.reason))

    async def _attach(
        self, of: tuple[str, str], bug: str, tree: str, failure: tuple[str, str]
    ) -> None:
        """Record that `bug` tracks the failure whose log is named (`failure` is log and reason)."""
        repository, ticket = of
        log, reason = failure
        steps, tests, why = await self._failing_names(repository, ticket, log)
        data: dict[str, Any] = {"bug": bug, "tree": tree, "steps": steps, "tests": tests}
        if why or reason:
            data["reason"] = why or reason
        await self._deps.tickets.record_activity(ticket, "flaky", data, by=ACTOR)

    async def _finish(self, row: CheckRun, attempt: Attempt) -> None:
        code = attempt.ran.code
        verdict = verdict_of(code, no_verdict=self._deps.stages.no_verdict(code))
        async with self._db() as store:
            await store.runs.finish(
                row.id,
                self._now(),
                verdict,
                {"exit_code": code, "log_path": attempt.ran.log, "tree_id": attempt.judged.tree_id},
            )

    async def _conclude(self, row: CheckRun, attempt: Attempt, extra: dict[str, Any]) -> None:
        """The record, flaky tracking after a pass, the status and the row, in that order."""
        data = await self._record(row, attempt, extra)
        if row.scope is not Scope.FAST:
            if attempt.ran.code == 0:
                await self._file_flaky(row.repository, row.subject, attempt.judged.tree)
            await self._post_final(row.repository, data)
        await self._finish(row, attempt)

    async def _lose(self, check_id: int) -> None:
        """End a run that has no verdict because its process was stopped."""

        async def lose() -> None:
            async with self._db() as store:
                await store.runs.lose(check_id, self._now())

        await self._cleanup(lose())
