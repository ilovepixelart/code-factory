"""How tickets relate: what blocks a ticket, what it blocks, its parent and children."""

from collections.abc import Mapping, Sequence
from typing import Any

from code_factory.tickets.models import Ticket

LANDED = frozenset({"merged", "released"})


class Relations:
    """The links among a set of tickets, built once however many cards ask."""

    def __init__(self, tickets: Sequence[Ticket], stages: Mapping[str, str]) -> None:
        self._stages = stages
        self._tickets = tickets
        self._known = {t.id for t in tickets}
        self._children: dict[str, list[str]] = {}
        for ticket in tickets:
            if ticket.parent:
                self._children.setdefault(ticket.parent, []).append(ticket.id)

    def _landed(self, ticket_id: str) -> bool:
        return self._stages.get(ticket_id) in LANDED

    def open_blockers(self, ticket: Ticket) -> list[str]:
        """The tickets `ticket` waits for that exist and have not landed."""
        return [b for b in ticket.blocked_by if b in self._known and not self._landed(b)]

    def children(self, ticket: Ticket) -> list[str]:
        """The ids of the tickets whose parent is `ticket`."""
        return self._children.get(ticket.id, [])

    def children_done(self, ticket: Ticket) -> int:
        """How many of `ticket`'s children have landed."""
        return sum(self._landed(child) for child in self.children(ticket))

    def link(self, ticket: Ticket) -> dict[str, Any]:
        """The ticket's links as its page shows them."""
        return {
            "open_blockers": self.open_blockers(ticket),
            "blocks": [t.id for t in self._tickets if ticket.id in t.blocked_by],
            "parent": ticket.parent,
            "children": len(self.children(ticket)),
            "children_done": self.children_done(ticket),
            "child_ids": self.children(ticket),
        }
