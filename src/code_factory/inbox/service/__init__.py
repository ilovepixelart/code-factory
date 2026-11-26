"""The inbox's public API: `InboxService`."""

from typing import Any

from code_factory.inbox.models import COUNTED, Sections
from code_factory.inbox.ports import PushStatus, Sources
from code_factory.inbox.rules import attention, build_page, hide_covered, oldest_first


class InboxService:
    """What waits on the owner, as the Inbox page and the board's badge read it."""

    def __init__(self, sources: Sources) -> None:
        self._sources = sources
        self._push: PushStatus | None = None

    def report_push(self, status: PushStatus) -> None:
        """Show `status` in the page's header: the push module calls this as it starts."""
        self._push = status

    async def _sections(self) -> Sections:
        found = hide_covered(await self._sources.sections())
        return {
            name: oldest_first(items, newest=name == "diagnoses") for name, items in found.items()
        }

    async def page(self) -> dict[str, Any]:
        """The `GET /api/inbox` answer."""
        push = None if self._push is None else await self._push.summary()
        return build_page(await self._sections(), None if push is None else push.model_dump())

    async def count(self) -> dict[str, Any]:
        """The `GET /api/inbox/count` answer: how many items wait and the newest sentence."""
        return attention(hide_covered(await self._sources.counted_sections()))

    async def waiting_ticket_ids(self) -> set[str]:
        """Tickets with an item in a counted section."""
        sections = hide_covered(await self._sources.counted_sections())
        return {i.ticket.id for name in COUNTED for i in sections.get(name, []) if i.ticket}


__all__ = ["InboxService"]
