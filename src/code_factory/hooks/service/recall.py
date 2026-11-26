"""At the start of a session: its standing rules and its ticket, handed back within the cap."""

from code_factory.hooks.models import RecalledText, RecallParts
from code_factory.hooks.ports import MemoryContext, MemoryRecall, TicketFacts
from code_factory.hooks.rules.recall import ticket_lines, within
from code_factory.hooks.service.base import Collaborators
from code_factory.platform.identity import Actor


class RecallMixin(Collaborators):
    """What a session reads again after a start, a restart or a compaction."""

    async def recall(
        self,
        *,
        cwd: str,
        actor: Actor | None,
        session_id: str = "",  # noqa: ARG002  # the route passes it on
    ) -> RecalledText | None:
        """The recall text, or `None` when there is nothing to say.

        The ticket is the actor's, else the one on the folder's branch; a folder outside every
        tracked repository is nothing, never an error. A run's delivery is recorded; an owner
        session's is not.
        """
        if actor is not None and actor.ticket_id is not None:
            ticket = await self._ports.tickets.get(actor.ticket_id)
            repository = ticket.repository
        elif actor is not None and actor.run_id is not None and actor.repository is not None:
            ticket, repository = None, actor.repository
        else:
            checkout = await self._ports.checkouts.of(cwd)
            if checkout is None:
                return None
            repository = checkout.repository
            ticket = await self._ports.tickets.by_branch(repository, checkout.branch)
        memory = await self._memory(repository, ticket, actor)
        lines = await self._ticket_lines(ticket)
        parts = RecallParts(
            memory=memory.kept,
            left=memory.left,
            ticket=lines,
            notices=[],
            overflow=memory.overflow,
            index=memory.index,
        )
        if not (memory.kept or memory.left or memory.overflow is not None or memory.index or lines):
            return None
        return within(parts)

    async def _memory(
        self, repository: str, ticket: TicketFacts | None, actor: Actor | None
    ) -> MemoryRecall:
        if ticket is None:
            return await self._ports.memory.recall(
                repository, MemoryContext(), ticket_id=None, run_id=None
            )
        paths = (
            await self._ports.checkouts.changed(repository, ticket.branch) if ticket.branch else []
        )
        context = MemoryContext(stage=ticket.stage, paths=paths, labels=ticket.labels)
        run_id = None if actor is None else actor.run_id
        return await self._ports.memory.recall(
            repository, context, ticket_id=ticket.id, run_id=run_id
        )

    async def _ticket_lines(self, ticket: TicketFacts | None) -> list[str]:
        if ticket is None:
            return []
        return ticket_lines(
            ticket.id,
            ticket.title,
            ticket.stage,
            ticket.branch,
            requirements=await self._ports.tickets.requirements(ticket.id),
            role_rules=[],
        )
