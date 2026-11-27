"""What delivery shows: pull requests, events and why a merge waits."""

from datetime import datetime

from code_factory.delivery.models import DeliveryEvent, PullHistory, PullView
from code_factory.delivery.repository import DeliveryRepository
from code_factory.delivery.service.base import Collaborators


class ReadingMixin(Collaborators):
    """Reads of the delivery tables."""

    async def pull(self, ticket_id: str) -> PullView | None:
        """The ticket's recorded pull request."""
        return await self._pull_of(ticket_id)

    async def pulls(self, ids: list[str]) -> dict[str, PullView]:
        """The recorded pull requests of the tickets, by id; one query."""
        async with self._uow() as session:
            return await DeliveryRepository(session).pulls(ids)

    async def events(self, ids: list[str]) -> dict[str, list[DeliveryEvent]]:
        """Each ticket's delivery events, oldest first; one query."""
        async with self._uow() as session:
            return await DeliveryRepository(session).events(ids)

    async def pushed_head(self, ticket_id: str) -> str | None:
        """The head of the open pull request, `None` without one."""
        pull = await self._pull_of(ticket_id)
        return pull.head if pull and pull.state == "open" and pull.head else None

    async def open_pulls(self) -> list[PullView]:
        """Every recorded open pull request."""
        async with self._uow() as session:
            return await DeliveryRepository(session).open_pulls()

    async def history(self, since: datetime, until: datetime) -> list[PullHistory]:
        """The pull requests that opened or merged in the window."""
        async with self._uow() as session:
            return await DeliveryRepository(session).history(since, until)

    async def known_merge(self, ticket: str, url: str) -> bool:
        """Whether delivery recorded this exact pull as merged for the ticket."""
        async with self._uow() as session:
            return await DeliveryRepository(session).known_merge(ticket, url)
