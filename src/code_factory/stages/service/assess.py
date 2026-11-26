"""Where a ticket stands and moving it: the checklist from stored facts, one column at a time."""

from collections.abc import Sequence
from datetime import datetime

from code_factory.platform.errors import BadRequestError, ConflictError, UnavailableError
from code_factory.stages import rules
from code_factory.stages.models import (
    EvidenceChange,
    MoveRefusedError,
    StageAssessment,
    StageEvent,
    StageMove,
)
from code_factory.stages.repository import StageRepository
from code_factory.stages.service.base import StageBase, opened_address, ticket_facts
from code_factory.stages.tables import StageFactsRow
from code_factory.tickets.models import Ticket, TicketFilter


def _assessment(
    ticket: Ticket,
    row: StageFactsRow | None,
    declared: str,
    release: str | None,
) -> StageAssessment:
    facts, own = ticket_facts(ticket, row)
    items = rules.derive_evidence(ticket.branch, facts, opened_address(ticket), release)
    derived = rules.stage_of(items)
    stage = rules.effective_stage(declared, derived)
    return StageAssessment(
        ticket_id=ticket.id,
        number=ticket.number,
        declared=declared,
        derived=derived,
        stage=stage,
        work_done=rules.work_done(items),
        checklist=items,
        refusals=rules.refusals(ticket.id, stage, items),
        hold=rules.card_hold(items, stage),
        landed=rules.is_landed(stage),
        facts_known=own and facts.known,
        git_unreadable=own and not facts.known,
        observed_at=row.observed_at if row is not None and own else None,
    )


class Assessing(StageBase):
    """Reads of a ticket's column and the moves that change it."""

    async def assess(self, ticket: str) -> StageAssessment:
        """Where the ticket stands, from its stored facts, its pull request and its release."""
        found = await self._ports.tickets.get(ticket)
        return (await self.assess_tickets([found]))[found.id]

    async def assess_many(self, ids: Sequence[str] | None = None) -> dict[str, StageAssessment]:
        """The assessments of these tickets (every live ticket without `ids`).

        A fixed number of queries whatever the number of tickets: the ticket list, the facts, the
        declarations and the releases.
        """
        wanted = None if ids is None else list(ids)
        return await self.assess_tickets(
            await self._ports.tickets.list(TicketFilter(archived=None, ids=wanted))
        )

    async def assess_tickets(self, found: Sequence[Ticket]) -> dict[str, StageAssessment]:
        """Assess the supplied ticket snapshots without fetching them a second time."""
        if not found:
            return {}
        numbers = [t.number for t in found]
        async with self._uow() as session:
            store = StageRepository(session)
            rows = await store.facts_of(numbers)
            declared = await store.declared_of(numbers)
        named = await self._ports.releases.naming([(t.repository, t.id) for t in found])
        return {
            t.id: _assessment(
                t,
                rows.get(t.number),
                declared.get(t.number, ""),
                named[(t.repository, t.id)].version if (t.repository, t.id) in named else None,
            )
            for t in found
        }

    async def is_reviewable(self, ticket: str) -> bool:
        """Whether a reviewer may look at the ticket's work: it is done and not yet in Review."""
        assessed = acted_on(await self.assess(ticket))
        return rules.reviewable(assessed.checklist, assessed.stage)

    async def move(self, ticket: str, target: str, by: str) -> StageMove:
        """Put the ticket in a column, one earned column at a time.

        `MoveRefusedError` with the sentence that says why when it may not go; `BadRequestError`
        for a name that is no column. A drop on the column the evidence already reached, with
        nothing declared, declares nothing.
        """
        moves = await self.move_many([ticket], target, by)
        return moves[0]

    async def move_many(self, ids: Sequence[str], target: str, by: str) -> list[StageMove]:
        """Move every ticket or none: the refusals are joined by `; ` before anything is written."""
        if target not in rules.NAMES:
            raise BadRequestError(f"unknown stage {target}")
        assessed = [acted_on(await self.assess(ticket)) for ticket in ids]
        refused = [a.refusals.get(target, "") for a in assessed]
        if any(refused):
            raise MoveRefusedError("; ".join(why for why in refused if why))
        moves = [_move_of(a, target) for a in assessed]
        now = self._clock()
        async with self._uow() as session:
            store = StageRepository(session)
            for move in moves:
                await store.set_declared(move.number, move.declared_after, by, now)
        for move in moves:
            await self._record_stage(move, by)
        return moves

    async def declare(
        self, ticket: str, declared: str, by: str, *, expect: str | None = None
    ) -> StageMove:
        """Pin the ticket to exactly the column named; an empty name clears the pin.

        With `expect` (empty: no declaration) the write happens only while the ticket still holds
        that declaration, else `ConflictError`: a change taken back must not overwrite one made
        since.

        No evidence is asked for: this is for a change that is taken back or an owner's edit, which
        `move` would refuse or only reorder, so it needs no readable git either.
        `BadRequestError` for a name that is no column.
        """
        if declared and declared not in rules.NAMES:
            raise BadRequestError(f"unknown stage {declared}")
        assessed = await self.assess(ticket)
        move = StageMove(
            ticket_id=assessed.ticket_id,
            number=assessed.number,
            from_stage=assessed.stage,
            to_stage=rules.effective_stage(declared, assessed.derived),
            declared_before=assessed.declared,
            declared_after=declared,
            changed=declared != assessed.declared,
        )
        async with self._uow() as session:
            store = StageRepository(session)
            if expect is None:
                await store.set_declared(move.number, declared, by, self._clock())
            elif not await store.set_declared_if(move.number, expect, declared, by, self._clock()):
                msg = f"{move.ticket_id} stage changed since it was read"
                raise ConflictError(msg)
        await self._record_stage(move, by)
        return move

    async def _record_stage(self, move: StageMove, by: str) -> None:
        """Append the `stage` record of a move that changed the column it was made from.

        The declaration and the record are two transactions, so a record lost after a committed
        declaration is made when the same move is made again: the column is then already the
        target, and the record runs from where the latest one left the ticket.
        """
        before = move.from_stage
        if move.from_stage == move.to_stage:
            page = await self._ports.activity.list_activity(
                move.ticket_id, kinds=["stage"], limit=1, newest_first=True
            )
            recorded = page.items[0].data.get("to") if page.items else None
            if recorded is None or recorded == move.to_stage:
                return
            before = str(recorded)
        data: dict[str, object] = {"from": before, "to": move.to_stage}
        await self._ports.tickets.record_activity(move.ticket_id, "stage", data, by=by)

    async def history(self, ticket: str) -> list[StageEvent]:
        """The ticket's stage records from every table of the module, oldest first."""
        number = await self._number(ticket)
        async with self._uow() as session:
            store = StageRepository(session)
            changes = await store.changes([number], None)
            rounds = await store.rounds_of(number)
            halts = await store.halts_of(number)
            waits = await store.waits_of(number)
            verdicts = await store.verdicts_of(number)
        events = [
            StageEvent(
                at=c.at,
                kind="evidence",
                sentence=f"{c.stage} {'present' if c.present else 'absent'}",
            )
            for c in changes
        ]
        events += [
            StageEvent(
                at=r.at, kind="fix_round", sentence=f"fix round for {r.reason} on {r.head[:7]}"
            )
            for r in rounds
        ]
        events += [
            StageEvent(
                at=h.at,
                kind="fix_halt",
                sentence=f"rounds ran out after {h.rounds} on {h.head[:7]}",
            )
            for h in halts
        ]
        events += [
            StageEvent(at=w.at, kind="fix_wait", sentence=rules.waits_on_main(w.step))
            for w in waits
        ]
        events += [
            StageEvent(
                at=v.at,
                kind=f"review.{v.outcome}",
                sentence=f"review {v.outcome} {v.head[:7]}".strip(),
            )
            for v in verdicts
        ]
        return sorted(events, key=lambda event: event.at)

    async def evidence_changes(
        self, ids: Sequence[str] | None = None, since: datetime | None = None
    ) -> list[EvidenceChange]:
        """The presence changes of these tickets (every ticket without `ids`), oldest first.

        Rows sharing one second are one observation.
        """
        named = await self._numbers(ids)
        async with self._uow() as session:
            rows = await StageRepository(session).changes(None if ids is None else named, since)
        return [
            EvidenceChange(
                ticket_id=named[r.ticket_number], stage=r.stage, present=r.present, at=r.at
            )
            for r in rows
            if r.ticket_number in named
        ]


def acted_on(assessed: StageAssessment) -> StageAssessment:
    """The assessment, unless git could not be read for the ticket: `UnavailableError` then.

    A ticket the observer has not reached yet is judged by what the ticket records.
    """
    if assessed.git_unreadable:
        raise UnavailableError(f"git facts of {assessed.ticket_id} are unknown")
    return assessed


def _move_of(assessed: StageAssessment, target: str) -> StageMove:
    declared = rules.declared_for_move(assessed.declared, assessed.derived, target)
    after = rules.effective_stage(declared, assessed.derived)
    return StageMove(
        ticket_id=assessed.ticket_id,
        number=assessed.number,
        from_stage=assessed.stage,
        to_stage=after,
        declared_before=assessed.declared,
        declared_after=declared,
        changed=declared not in {"", assessed.declared},
    )
