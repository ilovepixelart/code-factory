"""Which repositories a ticket may be filed in: the ones the board offers."""

from collections.abc import Set as AbstractSet

from code_factory.tickets.models import DEFAULT_REPOSITORY


def known_repository(name: str, *, tracked: AbstractSet[str], filed: AbstractSet[str]) -> bool:
    """Tracked, or holding a ticket already, or the first-ticket default while there is neither."""
    if name in tracked or name in filed:
        return True
    return name == DEFAULT_REPOSITORY and not tracked and not filed
