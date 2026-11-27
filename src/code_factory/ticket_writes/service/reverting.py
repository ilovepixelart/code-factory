"""Taking a change back: the handler of the `tickets.revert` undo kind."""

from typing import Any

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.ticket_writes.models import LINK_FIELDS
from code_factory.ticket_writes.rules import held_text, plan_update, revert_conflict
from code_factory.ticket_writes.service.base import NO_TICKET, WriteBase, write_plan
from code_factory.tickets.models import LinkGraph, TicketAddress
from code_factory.tickets.service import TicketUnit

NO_LINKS = LinkGraph(ids=[], parent_of={})


def _address(op: dict[str, Any]) -> TicketAddress:
    return TicketAddress(repository=op["repository"], id=op["id"])


class Reverting(WriteBase):
    """Puts back what a stored change left, while the guarded fields still hold what it left."""

    async def _revert(self, payload: dict[str, Any], by: str) -> None:
        """Undo every op of the payload or none.

        Field and column expectations are checked first (a conflict names the field and what it
        holds now). The columns go back next, each only while it still holds what the change left
        (the stages module writes in transactions of its own, and a column row cannot be written
        while the unit holds its ticket), then the field, rank and restore ops in one unit. When
        the unit or a later column is refused, the columns already put back are put back again.
        """
        ops: list[dict[str, Any]] = payload["ops"]
        stage_ops = [op for op in ops if op["op"] == "stage"]
        for op in stage_ops:
            await self._check_stage(op)
        repositories = sorted({op["repository"] for op in ops if "repository" in op})
        done: list[dict[str, Any]] = []
        try:
            for op in stage_ops:
                await self._put_back_stage(op, by)
                done.append(op)
            async with self._unit(repositories) as unit:
                for op in ops:
                    if op["op"] != "stage":
                        await self._apply(unit, op, by)
        except Exception:
            for op in reversed(done):
                await self._ports.stages.declare(
                    op["id"], op["expect"]["stage"], by, expect=op["to"] or ""
                )
            raise

    async def _put_back_stage(self, op: dict[str, Any], by: str) -> None:
        try:
            await self._ports.stages.declare(
                op["id"], op["to"] or "", by, expect=op["expect"]["stage"]
            )
        except ConflictError as lost:
            assessed = await self._ports.stages.assess(op["id"])
            held = assessed.declared
            raise ConflictError(revert_conflict(op, {"stage": held}) or str(lost)) from None

    async def _check_stage(self, op: dict[str, Any]) -> None:
        try:
            held = (await self._ports.stages.assess(op["id"])).declared
        except NotFoundError:
            raise NotFoundError(NO_TICKET) from None
        conflict = revert_conflict(op, {"stage": held})
        if conflict is not None:
            raise ConflictError(conflict)

    async def _apply(self, unit: TicketUnit, op: dict[str, Any], by: str) -> None:
        ref = _address(op)
        if op["op"] == "rank":
            await unit.set_ranks(ref.repository, {ref.id: op["to"]})
        elif op["op"] == "restore":
            await self._restore(unit, ref)
        else:
            await self._put_back(unit, ref, op, by)

    async def _restore(self, unit: TicketUnit, ref: TicketAddress) -> None:
        if await unit.restore(ref):
            return
        if await unit.get(ref) is not None:
            raise ConflictError(f"{ref.id} was already restored")
        raise NotFoundError(NO_TICKET)

    async def _put_back(
        self, unit: TicketUnit, ref: TicketAddress, op: dict[str, Any], by: str
    ) -> None:
        current = await unit.get(ref)
        if current is None:
            raise NotFoundError(NO_TICKET)
        conflict = revert_conflict(op, {name: held_text(current, name) for name in op["expect"]})
        if conflict is not None:
            raise ConflictError(conflict)
        graph = NO_LINKS
        if set(op["to"]) & set(LINK_FIELDS):
            graph = await unit.link_graph(ref.repository)
        plan = plan_update(current, op["to"], graph, self._ports.git.branch_refusal)
        if isinstance(plan, str):
            raise BadRequestError(plan)
        await write_plan(unit, ref, plan, by=by)
