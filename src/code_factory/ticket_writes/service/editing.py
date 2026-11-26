"""Editing a ticket: its fields, its rank and its links."""

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.ticket_writes.models import EDITABLE, UpdateResult
from code_factory.ticket_writes.rules import (
    held_text,
    link_change,
    one_line,
    plan_update,
    unknown_fields,
)
from code_factory.ticket_writes.service.base import NO_TICKET, WriteBase, undo_fields, write_plan
from code_factory.tickets.models import TicketAddress, TicketFields
from code_factory.undo.models import Changed

NEGATIVE_RANK = "a rank is not negative"


class Editing(WriteBase):
    """Update, set a rank, add and remove links."""

    async def update(self, ref: TicketAddress, fields: dict[str, str], by: str) -> UpdateResult:
        """Change the named fields; `changed` names those that differed.

        A named column is declared exactly, after the refusals the stages module holds for it.
        Archiving or restoring answers a notice and an undo.
        """
        held = await self._core(ref)
        refused = unknown_fields(fields, EDITABLE) or one_line(fields.items())
        if refused is not None:
            raise BadRequestError(refused)
        await self._branch_gone(ref.repository, fields.get("branch", "").strip(), held.branch)
        await self._stage_allowed(held.id, fields.get("stage", "").strip())
        async with self._unit([ref.repository]) as unit:
            current = await unit.get(ref)
            if current is None:
                raise NotFoundError("no such ticket")
            plan = plan_update(
                current,
                fields,
                await unit.link_graph(ref.repository),
                self._ports.git.branch_refusal,
            )
            if isinstance(plan, str):
                raise BadRequestError(plan)
            await write_plan(unit, ref, plan, by=by)
        changed = plan.changed
        if plan.stage and (await self._ports.stages.declare(ref.id, plan.stage, by)).changed:
            changed = [*changed, "stage"]
        if plan.archived is None:
            return UpdateResult(notice="", undo=None, changed=changed)
        verb = "Archived" if plan.archived else "Restored"
        back = undo_fields(
            ref,
            {"archived": held_text(current, "archived")},
            {"archived": "true" if plan.archived else ""},
        )
        offered = await self._offer([back], f"{verb} {ref.id}")
        return UpdateResult(notice=offered.notice, undo=offered.undo, changed=changed)

    async def _stage_allowed(self, ticket: str, stage: str) -> None:
        if not stage:
            return
        refusal = (await self._ports.stages.assess(ticket)).refusals.get(stage, "")
        if refusal:
            raise BadRequestError(refusal)

    async def set_rank(self, ref: TicketAddress, rank: int, by: str) -> None:
        """Put the card at `rank` and record it; a negative rank is refused."""
        if rank < 0:
            raise BadRequestError(NEGATIVE_RANK)
        async with self._unit([ref.repository]) as unit:
            if await unit.get(ref) is None:
                raise NotFoundError("no such ticket")
            if await unit.save_fields(ref, TicketFields(rank=rank)):
                await unit.record(ref, "field", {"name": "rank", "value": str(rank)}, by=by)

    async def add_link(self, ref: TicketAddress, kind: str, target: str, by: str) -> Changed:
        """Link `target` to the ticket as `kind` (`parent`, `child`, `blocked_by`, `blocks`)."""
        return await self._relink(ref, kind, target, by, add=True)

    async def remove_link(self, ref: TicketAddress, kind: str, target: str, by: str) -> Changed:
        """Take the link of `kind` to `target` away."""
        return await self._relink(ref, kind, target, by, add=False)

    async def _relink(
        self, ref: TicketAddress, kind: str, target: str, by: str, *, add: bool
    ) -> Changed:
        """Read both tickets, work out the link and write it under one hold of the repository.

        The link is the holder's whole list with one entry added or removed, so it is worked out
        from what the holder has once the lock is held: two links added at once both stay.
        """
        name = target.strip()
        async with self._unit([ref.repository]) as unit:
            own = await unit.get(ref)
            if own is None:
                raise NotFoundError(NO_TICKET)
            try:
                other = await unit.get(TicketAddress(repository=ref.repository, id=name))
            except BadRequestError:
                other = None
            change = link_change(own, other, kind, name, add=add)
            if isinstance(change, str):
                raise BadRequestError(change)
            holder = TicketAddress(repository=ref.repository, id=change.holder)
            current = own if change.holder == own.id else other
            if current is None:
                raise NotFoundError(NO_TICKET)
            plan = plan_update(
                current,
                {change.field: change.value},
                await unit.link_graph(ref.repository),
                self._ports.git.branch_refusal,
            )
            if isinstance(plan, str):
                raise BadRequestError(plan)
            await write_plan(unit, holder, plan, by=by)
        back = undo_fields(
            holder, {change.field: held_text(current, change.field)}, {change.field: change.value}
        )
        verb = "Linked" if add else "Unlinked"
        return await self._offer([back], f"{verb} {name} as {kind.replace('_', ' ')} of {ref.id}")
