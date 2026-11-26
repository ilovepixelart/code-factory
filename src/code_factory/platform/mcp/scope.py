"""Which ticket a call may touch: a run's own, a coordinator's repository, the owner's choice."""

from typing import Protocol

from code_factory.platform.errors import ForbiddenError
from code_factory.platform.identity import Actor, Role
from code_factory.platform.mcp import policy


class TicketRepositories(Protocol):
    """What the scope check needs of the tickets module, so no tool module imports another's.

    The tickets module registers its service under this key; a tool reads it from `Services`.
    """

    async def repository_of(self, ticket: str) -> str | None:
        """The repository the ticket belongs to, `None` when there is no such ticket."""
        ...


async def scope_ticket(
    actor: Actor, ticket_id: str | None, repositories: TicketRepositories
) -> str:
    """`policy.scope_ticket`, and for a coordinator also that the ticket is in its repository.

    A coordinator is bound to one repository. A ticket of another repository and one that does
    not exist are refused with the same sentence, so the answer reveals nothing about either.
    """
    ticket = policy.scope_ticket(actor, ticket_id)
    if (
        actor.role is Role.COORDINATOR
        and await repositories.repository_of(ticket) != actor.repository
    ):
        raise ForbiddenError(
            f"out_of_scope: this token is scoped to repository {actor.repository}; "
            f"{ticket} is not available to it."
        )
    return ticket
