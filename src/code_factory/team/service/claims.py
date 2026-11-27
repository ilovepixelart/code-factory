"""Claims on tickets: who holds what, the pick of an agent for a run, the keeper."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from code_factory.platform.errors import ConflictError, NotFoundError
from code_factory.team import rules
from code_factory.team.models import Ask, Claim, ClaimView, Lease, TeamRun
from code_factory.team.repository import LeaseRepository
from code_factory.team.service.base import ServiceBase, together

logger = logging.getLogger(__name__)


def _run_ids(leases: dict[str, Lease]) -> list[str]:
    return sorted({run for lease in leases.values() for run in lease.runs})


class Claims(ServiceBase):
    """The claim on each ticket (a lease): claim, heartbeat, release, expiry at 60 s."""

    @asynccontextmanager
    async def _exclusive(self) -> AsyncGenerator[LeaseRepository]:
        """A unit of work that holds the claims' locks: this process's, then the database's."""
        async with self._serial, self._uow() as session:
            repo = LeaseRepository(session)
            await repo.lock()
            yield repo

    async def _lease_runs(self, leases: dict[str, Lease]) -> list[TeamRun]:
        ids = _run_ids(leases)
        if not ids:
            return []
        return await self._read("the runs", self._ports().runs.runs_by_ids(ids))

    async def _decide(
        self,
        leases: dict[str, Lease],
        ticket_id: str,
        stage: str,
        now: float,
        *,
        flags: tuple[bool, bool],
    ) -> Claim:
        """The agent a run at `stage` takes on the ticket, or why it cannot start."""
        ports = self._ports()
        async with together() as group:
            asked = group.create_task(self._read("the ticket", ports.tickets.ticket_ask(ticket_id)))
            defined = group.create_task(self._read("the agents", ports.agents.team_agents()))
        ask_of, agents = asked.result(), defined.result()
        runs = await self._runs_for([ticket_id], agents, _run_ids(leases), now, ports=ports)
        try:
            rules.claim(leases, ticket_id, "", runs, now)
        except rules.ClaimHeld as held:
            raise ConflictError(str(held)) from held
        ask = Ask(
            key=ticket_id,
            stage=stage,
            kind=ask_of.kind,
            labels=ask_of.labels,
            runs=tuple(runs),
            now=now,
            other_model=flags[0],
            escalate=flags[1],
        )
        try:
            agent = rules.pick(agents, rules.busy(leases, runs, now), ask)
        except rules.NoAgent as refused:
            raise ConflictError(str(refused)) from refused
        return Claim(agent=agent, passed_over=tuple(rules.passed_over(agents, agent, ask)))

    async def claim_for_run(
        self,
        ticket_id: str,
        stage: str,
        *,
        other_model: bool = False,
        escalate: bool = False,
    ) -> Claim:
        """Claim the ticket for a run at `stage` and pick its agent, in one transaction.

        The module's advisory lock serialises claim and pick, so two tickets never take one free
        agent. `ConflictError` with the sentence for a held claim or a refusal; no row is left.
        """
        number = rules.claim_number(ticket_id)
        async with self._exclusive() as repo:
            now = self._seconds(None)
            decided = await self._decide(
                await repo.all(), ticket_id, stage, now, flags=(other_model, escalate)
            )
            lease_id = await repo.replace(number, decided.agent.name if decided.agent else "", now)
            return decided.model_copy(update={"lease_id": lease_id})

    async def start_refusal(
        self, ticket_id: str, stage: str, *, other_model: bool = False, escalate: bool = False
    ) -> str | None:
        """The claim-held or no-agent sentence a start would meet; `None` when it would start."""
        rules.claim_number(ticket_id)
        leases = await self._claims(None)
        try:
            await self._decide(
                leases, ticket_id, stage, self._seconds(None), flags=(other_model, escalate)
            )
        except ConflictError as refused:
            return str(refused)
        return None

    async def beat_start(self, ticket_id: str, lease_id: int) -> bool:
        """Keep the exact starting claim while it still holds."""
        number = rules.claim_number(ticket_id)
        async with self._exclusive() as repo:
            if await repo.id_for(number) != lease_id:
                return False
            leases = await repo.all([number])
            now = self._seconds(None)
            if not rules.holds(leases[ticket_id], await self._lease_runs(leases), now):
                return False
            await repo.beat([number], now)
            return True

    async def attach_run(self, ticket_id: str, run_id: str, *, lease_id: int | None = None) -> None:
        """Record a run under the ticket's claim; `NotFoundError` when it has no claim."""
        number = rules.claim_number(ticket_id)
        async with self._exclusive() as repo:
            if not await repo.attach(number, run_id, expected=lease_id):
                msg = f"{ticket_id} has no claim to record run {run_id} under; claim it first"
                raise NotFoundError(msg)

    async def end_claim(
        self, ticket_id: str, *, run_id: str | None = None, lease_id: int | None = None
    ) -> None:
        """Delete the ticket's claim; `NotFoundError` when it has none.

        With `run_id`, only a claim that run is recorded under: a run that ends after its claim was
        taken again must not delete the new one (`ConflictError`).
        """
        number = rules.claim_number(ticket_id)
        async with self._exclusive() as repo:
            if lease_id is not None and await repo.id_for(number) != lease_id:
                raise ConflictError("the ticket's starting claim changed")
            lease = (await repo.all([number])).get(ticket_id)
            if lease is None:
                raise NotFoundError(f"{ticket_id} has no claim")
            if run_id is not None and run_id not in lease.runs:
                msg = f"{ticket_id} is claimed again and run {run_id} is not under that claim"
                raise ConflictError(msg)
            await repo.delete(number)

    async def claim(self, ticket_id: str, holder: str) -> bool:
        """Claim the ticket for `holder` (a runner as `runner:<name>`); `False` while it holds."""
        number = rules.claim_number(ticket_id)
        async with self._exclusive() as repo:
            leases = await repo.all([number])
            now = self._seconds(None)
            try:
                rules.claim(leases, ticket_id, holder, await self._lease_runs(leases), now)
            except rules.ClaimHeld:
                return False
            await repo.replace(number, holder, now)
            return True

    async def _held_by(self, repo: LeaseRepository, ticket_id: str, holder: str) -> bool:
        """Whether `holder`'s claim on the ticket holds."""
        number = rules.claim_number(ticket_id)
        leases = await repo.all([number])
        lease = leases.get(ticket_id)
        if lease is None or lease.agent != holder:
            return False
        return rules.holds(lease, await self._lease_runs(leases), self._seconds(None))

    async def beat(self, ticket_id: str, holder: str) -> bool:
        """Beat the holder's claim while it holds; `False` for anyone else's or a lapsed one."""
        async with self._exclusive() as repo:
            if not await self._held_by(repo, ticket_id, holder):
                return False
            await repo.beat([rules.claim_number(ticket_id)], self._seconds(None))
            return True

    async def release(self, ticket_id: str, holder: str) -> bool:
        """Release the holder's claim while it holds; `False` for anyone else's or a lapsed one."""
        async with self._exclusive() as repo:
            if not await self._held_by(repo, ticket_id, holder):
                return False
            return await repo.delete(rules.claim_number(ticket_id))

    async def keep(self, now: float | None = None) -> int:
        """Beat the claims with an active run and delete those that no longer hold.

        Returns the number deleted.
        """
        at = self._seconds(now)
        async with self._exclusive() as repo:
            leases = await repo.all()
            kept = rules.kept(leases, await self._lease_runs(leases), at)
            dropped = [rules.claim_number(key) for key in leases if key not in kept]
            beaten = [
                rules.claim_number(key)
                for key, lease in kept.items()
                if lease.beat_at != leases[key].beat_at
            ]
            await repo.delete_many(dropped)
            await repo.beat(beaten, at)
        return len(dropped)

    async def run_keeper(self, interval: float = 5.0) -> None:
        """Keep the claims every `interval` seconds until cancelled; the first pass is one in.

        A pass that fails is logged and the loop goes on; cancellation is never swallowed.
        """
        while True:
            await asyncio.sleep(interval)
            try:
                await self.keep()
            except Exception:
                logger.exception("the team keeper pass failed")

    async def holders(self, ids: list[str]) -> dict[str, str]:
        """The agent holding each of these tickets, for defined agents whose claim holds."""
        leases = await self._claims(ids)
        runs = await self._lease_runs(leases)
        now = self._seconds(None)
        return {
            key: lease.agent
            for key, lease in leases.items()
            if lease.agent and rules.holds(lease, runs, now)
        }

    async def holder(self, ticket_id: str) -> str | None:
        """The defined agent holding the ticket, or `None`."""
        return (await self.holders([ticket_id])).get(ticket_id)

    async def _claims(self, ids: list[str] | None) -> dict[str, Lease]:
        numbers = None if ids is None else [rules.claim_number(i) for i in ids]
        async with self._uow() as session:
            return await LeaseRepository(session).all(numbers)

    async def busy(self) -> dict[str, str]:
        """The defined agents with a holding claim, each to its ticket's id."""
        leases = await self._claims(None)
        return rules.busy(leases, await self._lease_runs(leases), self._seconds(None))

    async def list_claims(self) -> list[ClaimView]:
        """Every claim by ticket and whether it holds, for the command line."""
        leases = await self._claims(None)
        runs = await self._lease_runs(leases)
        now = self._seconds(None)
        ordered = sorted(leases.items(), key=lambda item: rules.claim_number(item[0]))
        return [
            ClaimView(
                ticket_id=key,
                agent=lease.agent,
                runs=lease.runs,
                claimed_at=lease.claimed_at,
                beat_at=lease.beat_at,
                holds=rules.holds(lease, runs, now),
            )
            for key, lease in ordered
        ]

    async def force_release(self, ticket_id: str) -> None:
        """Free a stuck claim; `ConflictError` naming the run while one of its runs is active."""
        number = rules.claim_number(ticket_id)
        async with self._exclusive() as repo:
            leases = await repo.all([number])
            if ticket_id not in leases:
                raise NotFoundError(f"{ticket_id} has no claim")
            active = [run for run in await self._lease_runs(leases) if run.active]
            if active:
                msg = f"{ticket_id} has run {active[0].id} still running; stop the run first"
                raise ConflictError(msg)
            await repo.delete(number)
