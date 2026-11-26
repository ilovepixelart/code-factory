"""The sentences a write answers with and the entry a draft stands for before it is written."""

from datetime import date

from code_factory.memory.models import MemoryEntry, NewMemory
from code_factory.memory_extras.rules.budget import overflow
from code_factory.memory_extras.rules.constants import BUDGET

NAMED_CHARS = 50
ELLIPSIS = "…"
DRAFT_ID = "\x00new"


def named(statement: str) -> str:
    """The statement in quotes, cut to 50 characters with an ellipsis ending a cut one."""
    cut = statement if len(statement) <= NAMED_CHARS else statement[: NAMED_CHARS - 1] + ELLIPSIS
    return f'"{cut}"'


def over_budget(entries: list[MemoryEntry]) -> str | None:
    """The refusal naming how far the always-kept entries pass the budget, or None."""
    over = overflow(entries)
    if over == 0:
        return None
    return (
        f"the rules and decisions every session loads would take {over} characters over the "
        f"memory budget of {BUDGET:,}: merge, scope or retire one before adding another"
    )


def draft_entry(draft: NewMemory, today: date, *, proposed: bool) -> MemoryEntry:
    """The entry a draft would be, under an id no entry has."""
    return MemoryEntry(
        **draft.model_dump(),
        id=DRAFT_ID,
        date=today,
        reviewed="",
        proposed=proposed,
        verdict="",
        retired="",
        merged_into="",
        status="proposed" if proposed else "active",
        review_due="",
        stale=False,
        incomplete=False,
    )
