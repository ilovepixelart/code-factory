"""The observer: reads git for the live tickets, keeps the stored facts and evidence changes."""

import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta

from code_factory.stages import rules
from code_factory.stages.models import BranchFacts, ObserveReport, PresenceChange
from code_factory.stages.repository import StageRepository
from code_factory.stages.service.base import StageBase, opened_address, ticket_facts
from code_factory.tickets.models import Ticket, TicketFilter

logger = logging.getLogger(__name__)
LANDED_EVERY = timedelta(hours=1)
UNREADABLE = BranchFacts(known=False)


class Observing(StageBase):
    """Refreshes `stage_facts` and appends `evidence_changes`."""

    async def observe(self, ids: Sequence[str] | None = None) -> ObserveReport:
        """Read git for these tickets (every live one not landed without `ids`) and record it.

        A ticket whose git read failed keeps its old placement and loses its trust. Each ticket is
        one transaction under its lock, so two observers of one ticket append a change once.
        """
        live = await self._ports.tickets.list(TicketFilter(archived=False if ids is None else None))
        wanted = None if ids is None else set(ids)
        chosen = [t for t in live if wanted is None or t.id in wanted]
        if ids is None:
            chosen = await self._due(chosen)
        report = ObserveReport()
        by_repository: dict[str, list[Ticket]] = {}
        for ticket in chosen:
            by_repository.setdefault(ticket.repository, []).append(ticket)
        named = await self._ports.releases.naming([(t.repository, t.id) for t in chosen])
        for repository, tickets in by_repository.items():
            snapshot = self._clock()
            facts = await self._read(repository, tickets)
            for ticket in tickets:
                release = named.get((ticket.repository, ticket.id))
                delta = await self._record(
                    ticket,
                    facts.get(ticket.id, UNREADABLE),
                    release.version if release else None,
                    snapshot,
                )
                report = ObserveReport(
                    observed=report.observed + delta.observed,
                    unknown=report.unknown + delta.unknown,
                    changes=[*report.changes, *delta.changes],
                )
        return report

    async def _due(self, tickets: list[Ticket]) -> list[Ticket]:
        """The tickets not landed, and the landed ones whose facts are an hour old."""
        async with self._uow() as session:
            rows = await StageRepository(session).facts_of(t.number for t in tickets)
        now = self._clock()
        due = []
        for ticket in tickets:
            row = rows.get(ticket.number)
            fresh_landing = (
                row is not None
                and row.branch == ticket.branch
                and row.merged
                and now - row.observed_at < LANDED_EVERY
            )
            if not fresh_landing:
                due.append(ticket)
        return due

    async def _read(self, repository: str, tickets: list[Ticket]) -> dict[str, BranchFacts]:
        try:
            return await self._facts.read(repository, {t.id: t.branch for t in tickets})
        except Exception:
            logger.exception("the facts of repository %s cannot be read", repository)
            return {}

    async def _record(
        self, ticket: Ticket, found: BranchFacts, release: str | None, at: datetime
    ) -> ObserveReport:
        """Store what git said at `at`, unless a newer snapshot of the ticket is stored already.

        Two observers of one ticket can read git in one order and reach the lock in another: the
        older snapshot must not overwrite the newer or append a false reversal.
        """
        async with self._uow() as session:
            store = StageRepository(session)
            await store.lock(ticket.number)
            row = (await store.facts_of([ticket.number])).get(ticket.number)
            if row is not None and row.observed_at > at:
                return ObserveReport()
            if not found.known:
                await store.mark_unknown(ticket.number, ticket.branch, at)
                return ObserveReport(unknown=1)
            await store.save_facts(ticket.number, ticket.branch, found, at)
            stored = (await store.facts_of([ticket.number]))[ticket.number]
            facts, _ = ticket_facts(ticket, stored)
            items = rules.derive_evidence(ticket.branch, facts, opened_address(ticket), release)
            seen = await store.last_presence(ticket.number)
            changes = [(i.stage, i.present) for i in items if seen.get(i.stage, False) != i.present]
            await store.append_changes(ticket.number, changes, at)
        made = [PresenceChange(ticket_id=ticket.id, stage=s, present=p) for s, p in changes]
        return ObserveReport(observed=1, changes=made)

    async def run_observer(self, interval: float, stop: asyncio.Event | None = None) -> None:
        """Observe every `interval` seconds until `stop` is set or the task is cancelled.

        The first pass is one interval in. A pass that fails is logged and the loop goes on;
        cancellation is never swallowed.
        """
        halt = stop or asyncio.Event()
        while not await _stopped(halt, interval):
            try:
                await self.observe()
            except Exception:
                logger.exception("the stage observer's pass failed")


async def _stopped(halt: asyncio.Event, interval: float) -> bool:
    """Wait up to `interval` seconds; whether `halt` was set in that time."""
    try:
        async with asyncio.timeout(interval):
            await halt.wait()
    except TimeoutError:
        return False
    return True
