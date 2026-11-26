"""Whether an entry still holds. `now` is a day number from `platform.text.epoch_day`."""

from collections.abc import Callable
from collections.abc import Set as AbstractSet

from code_factory.memory.models import MemoryEntry
from code_factory.memory_extras.rules.constants import REVIEW_DAYS, STALE_DAYS, UNUSED_DAYS
from code_factory.memory_extras.rules.days import last_review_day, written_day
from code_factory.platform.text import day_text, iso_date_days


def guard_state(entry: MemoryEntry, defined: AbstractSet[str]) -> str:
    """The state of a lesson's guard; empty for the other kinds.

    `enforced` when it names a defined test, `missing` when it names anything else, `none` when
    blank.
    """
    guard = entry.guard.strip()
    if entry.kind != "lesson":
        return ""
    if not guard:
        return "none"
    return "enforced" if guard in defined else "missing"


def stale(entry: MemoryEntry, now: int) -> bool:
    """Whether more than 30 days passed since the last review, or the writing."""
    last = last_review_day(entry)
    return last is not None and now - last > STALE_DAYS


def review_due(entry: MemoryEntry) -> str:
    """The day the entry falls due for review (`YYYY-MM-DD`), empty when the review is no date."""
    last = last_review_day(entry)
    return "" if last is None else day_text(last + REVIEW_DAYS)


def overdue(entry: MemoryEntry, now: int) -> bool:
    """Whether the review fell due before `now`; a proposal waits in the Inbox, never here."""
    due = review_due(entry)
    return not entry.proposed and bool(due) and due < day_text(now)


def incomplete(entry: MemoryEntry) -> bool:
    """Whether the statement, the why or the source is blank."""
    return any(not text.strip() for text in (entry.statement, entry.why, entry.source))


def loaded(entry: MemoryEntry, defined: AbstractSet[str]) -> bool:
    """Whether sessions load the entry: active, not proposed, and not a lesson a test enforces."""
    return not entry.retired and not entry.proposed and guard_state(entry, defined) != "enforced"


def lapsed(entry: MemoryEntry, today: str, merged: Callable[[str], bool]) -> bool:
    """Whether `expires` is before `today`, or the `until` ticket merged."""
    expires, until = entry.expires.strip(), entry.until.strip()
    return (bool(expires) and expires < today) or (bool(until) and merged(until))


def unused(entry: MemoryEntry, received: str | None, now: int) -> bool:
    """Whether more than 30 days passed since a run last received the entry.

    `received` is that day, or None when none did and the writing counts. A day that is not a
    date is never unused.
    """
    last = written_day(entry) if received is None else iso_date_days(received)
    return last is not None and now - last > UNUSED_DAYS
