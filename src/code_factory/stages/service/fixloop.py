"""The board's checks on a head and the fix loop: attempts, rounds, halts and the agent's task."""

from collections.abc import Sequence
from datetime import datetime

from code_factory.platform.errors import BadRequestError
from code_factory.platform.text import masked
from code_factory.stages import rules
from code_factory.stages.models import (
    ChecksState,
    FixLedger,
    FlakyReading,
    PullView,
    RoundDecision,
)
from code_factory.stages.ports import LogReader
from code_factory.stages.repository import StageRepository
from code_factory.stages.service.base import StageBase

REASONS = ("ci", "review", "conflict")


class FixLoop(StageBase):
    """The board's checks on a head, and the fix loop's records kept under the ticket's lock."""

    _log_reader: LogReader | None = None

    async def repair_requests(self, tickets: Sequence[str]) -> dict[str, list[float]]:
        """Recorded repair requests as epoch seconds for the named tickets."""
        numbers = await self._numbers(tickets)
        result: dict[str, list[float]] = {ticket: [] for ticket in numbers.values()}
        if numbers:
            async with self._uow() as session:
                for number, at in await StageRepository(session).repair_requests(list(numbers)):
                    result[numbers[number]].append(at.timestamp())
        return result

    def bind_log_reader(self, reader: LogReader) -> None:
        """Let `checks_task` quote the log a `checks` record names; the checks module calls this."""
        self._log_reader = reader

    async def checks_state(
        self, ticket: str, head: str, now: datetime | None = None
    ) -> ChecksState:
        """What the board's checks on `head` say: their code, whether settled, the retry due."""
        records = await self._records(ticket)
        found = rules.own_checks(records, head)
        return ChecksState(
            exit_code=None if found is None else found[1],
            settled=rules.settled(records, head),
            rerun_pending=rules.rerun_pending(records, head),
            container_retry_due=rules.container_retry_due(records, head, now or self._clock()),
            failed_steps=[] if found is None else rules.failed_steps(found[0]),
        )

    async def flaky(self, ticket: str, tree: str) -> FlakyReading | None:
        """The failure that makes a pass on `tree` flaky and the sentence that files it."""
        records = await self._records(ticket)
        failed = rules.flaky_failure(records, tree)
        if failed is None:
            return None
        return FlakyReading(log=failed, reason=rules.flaky_reason(records, ticket, tree, failed))

    async def begin_fix_round(  # noqa: PLR0913  # the head and what it was wanted for, all named
        self,
        ticket: str,
        head: str,
        reason: str,
        *,
        review: str = "",
        run_id: str | None = None,
        can_start: bool = True,
        now: datetime | None = None,
    ) -> RoundDecision:
        """Decide whether the head gets a fix round, in one transaction under the ticket's lock.

        `given` when the round exists (one per failed head, one per review stamp), else `halted`
        (recorded once) when the ticket already has `[agents] fix_rounds` rounds, else `waiting`
        when no run can start (nothing recorded), else the round is recorded and `started`.
        """
        if reason not in REASONS or not head:
            raise BadRequestError(f"a fix round needs a head and a reason of {', '.join(REASONS)}")
        found = await self._ports.tickets.get(ticket)
        cap = (await self._agents(found.repository)).fix_rounds
        at = now or self._clock()
        async with self._uow() as session:
            store = StageRepository(session)
            await store.lock(found.number)
            rounds = await store.rounds_of(found.number)
            given = rules.round_given(rounds, PullView(head=head, reviewed=review), reason)
            outcome = rules.decide_round(len(rounds), cap, can_start=can_start, given=given)
            if outcome == "halted":
                await store.add_halt(found.number, head, reason, len(rounds), at)
            if outcome == "started":
                await store.add_round(
                    found.number, head, reason, review=review, run_id=run_id or "", now=at
                )
        return RoundDecision(outcome=outcome, rounds=len(rounds) + (outcome == "started"))

    async def round_given(self, ticket: str, pull: PullView, reason: str) -> bool:
        """Whether a fix round for `reason` was given for what sends `pull` back."""
        number = await self._number(ticket)
        async with self._uow() as session:
            rounds = await StageRepository(session).rounds_of(number)
        return rules.round_given(rounds, pull, reason)

    async def rounds_out(self, ticket: str, pull: PullView) -> str | None:
        """What the owner is told once the rounds ran out on the pull request's head."""
        number = await self._number(ticket)
        async with self._uow() as session:
            halts = await StageRepository(session).halts_of(number)
        return rules.rounds_out(halts, await self._records(ticket), pull)

    async def halted_at(self, ticket: str, head: str) -> datetime | None:
        """When the ticket's fix rounds last ran out on `head`."""
        number = await self._number(ticket)
        async with self._uow() as session:
            halts = await StageRepository(session).halts_of(number)
        return rules.halted_at(halts, head)

    async def note_waits_on_main(self, ticket: str, head: str, step: str, main_commit: str) -> None:
        """Record the step `head` fails on that main fails too; the latest write wins."""
        number = await self._number(ticket)
        async with self._uow() as session:
            await StageRepository(session).set_wait(number, head, step, main_commit, self._clock())

    async def waits_on_main(self, ticket: str, head: str) -> str | None:
        """`Fails on main too at <step>` while the head waits for main; `None` without a wait."""
        number = await self._number(ticket)
        async with self._uow() as session:
            waits = await StageRepository(session).waits_of(number)
        step = next((w.step for w in waits if w.head == head), None)
        return None if step is None else rules.waits_on_main(step)

    async def checks_task(self, ticket: str, head: str) -> str | None:
        """What the ticket's agent is told when the board's checks failed on `head`.

        From the latest `checks` record of the head: its failed steps and the failing lines of its
        log, masked. `None` when the head has no record or its checks passed.
        """
        found = rules.own_checks(await self._records(ticket), head)
        if found is None or found[1] == 0:
            return None
        check, code = found
        lines: list[str] = []
        if self._log_reader is not None and check.text("log"):
            text = await self._log_reader.read(check.text("log"))
            lines = rules.read_log(text).failing_lines if text is not None else []
        return rules.checks_task(head, code, rules.failed_steps(check), lines, masked)

    async def ledger(self, ticket: str) -> FixLedger:
        """The ticket's fix rounds, halts, waits and review verdicts."""
        number = await self._number(ticket)
        async with self._uow() as session:
            store = StageRepository(session)
            return FixLedger(
                rounds=await store.rounds_of(number),
                halts=await store.halts_of(number),
                waits=await store.waits_of(number),
                verdicts=await store.verdicts_of(number),
            )
