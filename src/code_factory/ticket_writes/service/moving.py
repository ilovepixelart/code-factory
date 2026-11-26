"""Moving cards between columns and one change to several of them."""

from collections.abc import Mapping, Sequence
from typing import Any

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.stages.models import StageMove
from code_factory.ticket_writes.rules import (
    ONE_ACTION,
    bulk_change,
    bulk_choice,
    bulk_notice,
    check_bulk,
    drop_groups,
    plan_update,
    rank_positions,
)
from code_factory.ticket_writes.service.base import NO_TICKET, WriteBase, undo_fields, write_plan
from code_factory.tickets.models import LinkGraph, TicketAddress, TicketCore
from code_factory.undo.models import Changed

NO_LINKS = LinkGraph(ids=[], parent_of={})


def _stage_op(move: StageMove) -> dict[str, Any]:
    return {
        "op": "stage",
        "id": move.ticket_id,
        "to": move.declared_before,
        "expect": {"stage": move.declared_after},
    }


def _entered(move: StageMove) -> bool:
    return bool(move.declared_after) and move.declared_after != move.declared_before


def parse_ref(key: str) -> TicketAddress:
    """The ticket `repository/id` names."""
    repository, _, ticket = key.partition("/")
    return TicketAddress(repository=repository.strip(), id=ticket.strip())


class Moving(WriteBase):
    """Move a card and its column's order; change many cards at once."""

    async def move(self, ref: TicketAddress, stage: str, order: Sequence[str], by: str) -> Changed:
        """Move the ticket to `stage`, then number the cards of `order` (`repository/id`).

        The column move is the stages module's and may be refused; the ranks that follow are
        cosmetic and skip any entry that names no ticket. An empty `stage` clears the declaration.
        An undo is offered only when the move pinned the card to a column it was not pinned to.
        """
        await self._core(ref)
        if stage:
            moved = await self._ports.stages.move(ref.id, stage, by)
        else:
            moved = await self._ports.stages.declare(ref.id, "", by)
        before = await self._rank(order)
        if not _entered(moved):
            return Changed(notice="", undo=None)
        return await self._offer(
            [_stage_op(moved), *before], f"Moved {ref.id} to {stage.capitalize()}"
        )

    async def _rank(self, order: Sequence[str]) -> list[dict[str, Any]]:
        """Number each repository's cards of the drop; the ranks they held, as undo ops."""
        groups = drop_groups(order)
        back: list[dict[str, Any]] = []
        async with self._unit([repository for repository, _ in groups]) as unit:
            for repository, ids in groups:
                held: dict[str, int] = {}
                for ticket in ids:
                    try:
                        found = await unit.get(TicketAddress(repository=repository, id=ticket))
                    except BadRequestError:
                        continue
                    if found is not None:
                        held[ticket] = found.rank
                changes = rank_positions(ids, held)
                await unit.set_ranks(repository, changes)
                back += [
                    {"op": "rank", "repository": repository, "id": t, "to": held[t]}
                    for t in changes
                ]
        return back

    async def bulk_request(self, body: Mapping[str, Any], by: str) -> Changed:
        """A bulk change as the app sends it: one action and the `repository/id` of each ticket."""
        choice = bulk_choice(body)
        if isinstance(choice, str):
            raise BadRequestError(choice)
        return await self.bulk(
            [parse_ref(key) for key in choice.tickets], choice.field, choice.value, by
        )

    async def bulk(self, refs: Sequence[TicketAddress], field: str, value: str, by: str) -> Changed:
        """Apply one change to every ticket or to none; one undo takes all of it back."""
        value = value.strip()
        if not refs:
            raise BadRequestError(ONE_ACTION)
        refused = check_bulk(field, value)
        if refused is not None:
            raise BadRequestError(refused)
        once = {(ref.repository, ref.id): ref for ref in refs}
        found = [await self._core(ref) for ref in once.values()]
        notice = bulk_notice(field, value, len(found))
        if field == "stage":
            moves = await self._ports.stages.move_many([t.id for t in found], value, by)
            return await self._offer([_stage_op(m) for m in moves if m.changed], notice)
        return await self._offer(await self._bulk_fields(found, field, value, by), notice)

    async def _bulk_fields(
        self, found: list[TicketCore], field: str, value: str, by: str
    ) -> list[dict[str, Any]]:
        ops: list[dict[str, Any]] = []
        async with self._unit(sorted({t.repository for t in found})) as unit:
            for ticket in found:
                ref = TicketAddress(repository=ticket.repository, id=ticket.id)
                current = await unit.get(ref)
                if current is None:
                    raise NotFoundError(NO_TICKET)
                name, new, old = bulk_change(current, field, value)
                plan = plan_update(current, {name: new}, NO_LINKS, self._ports.git.branch_refusal)
                if isinstance(plan, str):
                    raise BadRequestError(plan)
                await write_plan(unit, ref, plan, by=by)
                if new != old:
                    ops.append(undo_fields(ref, {name: old}, {name: new}))
        return ops
