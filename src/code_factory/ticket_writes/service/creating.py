"""Filing a ticket and copying one."""

from code_factory.platform.errors import BadRequestError
from code_factory.ticket_writes.models import CREATE_FIELDS, Record
from code_factory.ticket_writes.rules import (
    one_line,
    plan_create,
    unknown_fields,
    with_question,
)
from code_factory.ticket_writes.service.base import WriteBase
from code_factory.tickets.models import NewTicket, TicketAddress

COPY_FIELDS = ("type", "description", "priority", "assignee", "due", "e2e", "tests")


class Creating(WriteBase):
    """Create and duplicate."""

    async def create(
        self,
        repository: str,
        fields: dict[str, str],
        by: str,
        *,
        ask_duplicates: bool = True,
    ) -> TicketAddress:
        """File a ticket in `repository`; the first refusal wins and nothing is written.

        `ask_duplicates` appends the question about open tickets with a like title to the
        description, when a duplicate question is bound.
        """
        await self._known_repository(repository)
        if fields.get("stage", "").strip() not in {"", "spec"}:
            msg = "a new ticket starts in Spec"
            raise BadRequestError(msg)
        refused = unknown_fields(fields, CREATE_FIELDS) or one_line(fields.items())
        if refused is not None:
            raise BadRequestError(refused)
        await self._branch_gone(repository, fields.get("branch", "").strip(), "")
        asked = await self._asked(repository, fields) if ask_duplicates else fields
        async with self._unit([repository]) as unit:
            graph = await unit.link_graph(repository)
            plan = plan_create(repository, asked, graph, self._ports.git.branch_refusal)
            if isinstance(plan, str):
                raise BadRequestError(plan)
            ref = await unit.insert(plan.ticket)
            for record in plan.activity:
                await unit.record(ref, record.kind, record.data, by=by)
            if plan.branch:
                await unit.set_branch(ref, plan.branch)
            if plan.archived:
                await unit.set_archived(ref, archived=True)
        return ref

    async def _asked(self, repository: str, fields: dict[str, str]) -> dict[str, str]:
        title = fields.get("title", "").strip()
        if self._duplicate_question is None or not title:
            return fields
        question = await self._duplicate_question(repository, title)
        if not question:
            return fields
        return {**fields, "description": with_question(fields.get("description", ""), question)}

    async def duplicate(self, ref: TicketAddress, by: str) -> TicketAddress:
        """A copy of the ticket's title and card, filed fresh: no branch, stage, links or budget."""
        original = await self._core(ref)
        copy = NewTicket.model_validate(
            {
                "repository": original.repository,
                "title": f"{original.title} (copy)",
                "labels": original.labels,
                **{name: getattr(original, name) for name in COPY_FIELDS},
            }
        )
        async with self._unit([original.repository]) as unit:
            made = await unit.insert(copy)
            record = Record(kind="created", data={"type": original.type, "from": original.id})
            await unit.record(made, record.kind, record.data, by=by)
        return made
