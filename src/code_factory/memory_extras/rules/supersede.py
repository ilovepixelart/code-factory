"""Which entries a new entry retires: the ids it supersedes."""

from collections.abc import Sequence
from collections.abc import Set as AbstractSet

from code_factory.memory.models import MemoryEntry
from code_factory.platform.errors import BadRequestError


def superseded_reason(by_id: str) -> str:
    """The reason a superseded entry retires with."""
    return f"superseded by {by_id}"


def superseded(entries: Sequence[MemoryEntry]) -> dict[str, str]:
    """Each active entry another active entry supersedes, with the id of the one that does.

    A proposal supersedes nothing until the owner approves it.
    """
    active = [entry for entry in entries if not entry.retired]
    ids = {entry.id for entry in active}
    found: dict[str, str] = {}
    for by in (entry for entry in active if not entry.proposed):
        found.update({name: by.id for name in by.supersedes if name in ids})
    return found


def plan_supersession(
    by_id: str, names: Sequence[str], active_ids: AbstractSet[str], retired_ids: AbstractSet[str]
) -> list[str]:
    """The ids that retire because `by_id` supersedes `names`; one already retired is skipped.

    Raises:
        BadRequestError: An entry names itself, or an id that is no entry.
    """
    retire = []
    for name in names:
        if name == by_id:
            raise BadRequestError("an entry cannot supersede itself")
        if name in active_ids:
            retire.append(name)
        elif name not in retired_ids:
            raise BadRequestError(f"no entry {name} to supersede")
    return retire
