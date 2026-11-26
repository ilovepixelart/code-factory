"""Days as ordinals: the one place an entry's date text becomes a number."""

from code_factory.memory.models import MemoryEntry
from code_factory.platform.text import iso_date_days


def written_day(entry: MemoryEntry) -> int:
    """The day the entry was written."""
    return entry.date.toordinal()


def last_review_day(entry: MemoryEntry) -> int | None:
    """The day of the last review, else of the writing; None when the review is not a date."""
    if not entry.reviewed:
        return written_day(entry)
    return iso_date_days(entry.reviewed)
