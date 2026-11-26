"""What the inbox reads of other modules: each section's items, already shaped."""

from typing import Protocol

from code_factory.inbox.models import PushState, Sections


class Sources(Protocol):
    """Every section's items from their owners."""

    async def sections(self) -> Sections:
        """The items of each section, unordered."""
        ...

    async def counted_sections(self) -> Sections:
        """Only the facts needed for the badge and the waiting ticket ids."""
        ...


class PushStatus(Protocol):
    """Where items are pushed and the last failure; None without a target."""

    async def summary(self) -> PushState | None:
        """The Inbox header's push line."""
        ...
