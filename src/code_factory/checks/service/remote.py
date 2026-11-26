"""Checks taken by a runner on another machine: offers, claims, results."""

import logging
from collections.abc import Sequence
from pathlib import Path

from code_factory.checks.models import MAIN, Claim, Judged, MainRecord, RunnerResult, Scope
from code_factory.checks.rules import (
    Refusal,
    cause_before_any_step,
    checks_record,
    clean_log_tail,
    complete_main,
    failed_step,
    refusal_sentence,
    tree_name,
)
from code_factory.checks.service.base import ACTOR
from code_factory.checks.service.queries import QueryMixin
from code_factory.platform.errors import BadRequestError, CodeFactoryError, ConflictError

logger = logging.getLogger(__name__)
TAIL_BYTES = 65_536


class RemoteMixin(QueryMixin):
    """What the runner routes call."""

    async def left_to_runners(self, repository: str, subject: str, head: str) -> bool:
        """Whether the board leaves the checks of the head to a runner: a claim or an offer."""
        now = self._now()
        async with self._db() as store:
            if await store.remote.declined(repository, subject, head, now):
                return False
            if await store.remote.claimed(repository, subject, head, now):
                return True
            return await store.remote.offered(repository, now)

    async def main_left_to_runners(self, repository: str, tip: str) -> bool:
        """Whether main's run on `tip` is a runner's: no run of the tip is recorded yet."""
        async with self._db() as store:
            recorded = await store.records.main(repository)
        if recorded is not None and recorded.commit == tip:
            return False
        return await self.left_to_runners(repository, MAIN, tip)

    async def claim_for_runner(self, runner: str, repositories: Sequence[str]) -> Claim | None:
        """Offer for `runner` and claim the first head of the named repositories it may check.

        An open pull request's head whose checks are not settled, which the board does not run
        itself and no runner gave back; else main's tip when no run of it is recorded.
        """
        now = self._now()
        named = list(repositories)
        async with self._db() as store:
            await store.remote.offer(runner, named, now)
        tracked = {record.name for record in await self._deps.repositories.list()}
        wanted = [name for name in named if name in tracked]
        for repository in wanted:
            found = await self._claim_pull(runner, repository)
            if found is not None:
                return found
        for repository in wanted:
            found = await self._claim_main(runner, repository)
            if found is not None:
                return found
        return None

    async def _claim_pull(self, runner: str, repository: str) -> Claim | None:
        async with self._db() as store:
            active = {row.subject for row in await store.runs.active(repository)}
        for pull in await self._deps.forge.open_pull_heads(repository):
            if pull.ticket_id in active:
                continue
            state = await self._deps.stages.checks_state(pull.ticket_id, pull.head, self._now())
            if state.settled:
                continue
            if await self._won(runner, repository, pull.ticket_id, pull.head):
                tree_id = await self._deps.git.tree_id(repository, pull.head)
                return Claim(
                    repository=repository, id=pull.ticket_id, head=pull.head, tree_id=tree_id
                )
        return None

    async def _claim_main(self, runner: str, repository: str) -> Claim | None:
        config = await self._config(repository)
        tip = await self._deps.git.base_tip(repository)
        if tip is None or config.commands[Scope.FULL] is None:
            return None
        async with self._db() as store:
            recorded = await store.records.main(repository)
            active = {row.subject for row in await store.runs.active(repository)}
        if (recorded is not None and recorded.commit == tip) or MAIN in active:
            return None
        if await self._won(runner, repository, MAIN, tip):
            tree_id = await self._deps.git.tree_id(repository, tip)
            return Claim(repository=repository, id=MAIN, head=tip, tree_id=tree_id)
        return None

    async def _won(self, runner: str, repository: str, subject: str, head: str) -> bool:
        now = self._now()
        async with self._db() as store:
            if await store.remote.declined(repository, subject, head, now):
                return False
            return await store.remote.claim(repository, subject, head, f"runner:{runner}", now)

    async def beat(self, runner: str, repository: str, subject: str, head: str) -> bool:
        """Keep the claim `runner` holds on the head; False when it does not hold one."""
        async with self._db() as store:
            return await store.remote.beat(
                repository, subject, head, f"runner:{runner}", self._now()
            )

    async def release(self, runner: str, repository: str, subject: str, head: str) -> bool:
        """Give the claim up: the board checks that head itself from now on."""
        now = self._now()
        async with self._db() as store:
            freed = await store.remote.release(repository, subject, head, f"runner:{runner}", now)
            if freed:
                await store.remote.decline(repository, subject, head, now)
        return freed

    async def _refuse(
        self, runner: str, claimed: tuple[str, str, str], kind: Refusal, *, give_up: bool = True
    ) -> ConflictError:
        repository, subject, head = claimed
        if give_up:
            await self.release(runner, repository, subject, head)
        return ConflictError(refusal_sentence(kind, subject))

    async def _head_moved(self, repository: str, subject: str, claimed: str) -> bool:
        if subject == MAIN:
            return await self._deps.git.base_tip(repository) != claimed
        pulls = await self._deps.forge.open_pull_heads(repository)
        return next((p.head for p in pulls if p.ticket_id == subject), None) != claimed

    async def accept(
        self, runner: str, repository: str, subject: str, claimed_head: str, result: RunnerResult
    ) -> None:
        """Take a runner's result for the head it claimed, and record it as the board's own.

        Only while the runner holds the claim, the pull request still has that head, the result is
        for it and the tree checked is its tree; a refusal records nothing and, but for a claim
        that is not the runner's, gives the claim up.
        """
        if len(result.log_tail.encode()) > TAIL_BYTES:
            msg = f"the log tail holds over {TAIL_BYTES} bytes"
            raise BadRequestError(msg)
        claimed = (repository, subject, claimed_head)
        if not await self.beat(runner, repository, subject, claimed_head):
            raise await self._refuse(runner, claimed, "not_yours", give_up=False)
        if await self._head_moved(repository, subject, claimed_head):
            raise await self._refuse(runner, claimed, "head_moved")
        if result.head != claimed_head:
            raise await self._refuse(runner, claimed, "other_head")
        expected = await self._deps.git.tree_id(repository, claimed_head)
        if not expected or result.tree_id != expected:
            raise await self._refuse(runner, claimed, "tree_differs")
        log = self._logs.path_for(repository, subject, int(self._now().timestamp()))
        await self._logs.write(log, clean_log_tail(result.log_tail))
        if subject == MAIN:
            await self._record_remote_main(repository, claimed_head, result.exit_code, log)
        else:
            await self._record_remote_ticket(repository, subject, expected, result, log)
        await self.release_quietly(runner, claimed)

    async def release_quietly(self, runner: str, claimed: tuple[str, str, str]) -> None:
        """Free the claim after a result; the head is not declined, it is checked."""
        repository, subject, head = claimed
        async with self._db() as store:
            await store.remote.release(repository, subject, head, f"runner:{runner}", self._now())

    async def _record_remote_main(self, repository: str, commit: str, code: int, log: Path) -> None:
        text = await self._logs.text_of(log) or ""
        reading = self._deps.stages.read_log(text)
        run = MainRecord(
            repository=repository, commit=commit, exit_code=code, log=str(log), at=self._now()
        )
        step = ""
        if code != 0:
            step = failed_step(reading.reported_steps) or cause_before_any_step(text)
        async with self._db() as store:
            previous = await store.records.main(repository)
            done = complete_main(previous, run, step=step, reason=reading.failure_reason)
            await store.records.put_main(done)

    async def _record_remote_ticket(
        self, repository: str, ticket: str, tree_id: str, result: RunnerResult, log: Path
    ) -> None:
        text = await self._logs.text_of(log)
        reading = None if text is None else self._deps.stages.read_log(text)
        judged = Judged(head=result.head, tree=tree_name(result.head), tree_id=tree_id)
        data = checks_record(judged, result.exit_code, str(log), reading, text=text)
        try:
            await self._deps.tickets.record_activity(ticket, "checks", data, by=ACTOR)
        except CodeFactoryError:
            logger.warning("the checks of %s could not be recorded", ticket, exc_info=True)
            raise
        if result.exit_code == 0:
            await self._file_flaky(repository, ticket, judged.tree)
        await self._post_final(repository, data)
