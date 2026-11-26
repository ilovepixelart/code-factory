"""The words and numbers a card says about a ticket's own fields."""

import math
import re
from datetime import UTC, date, datetime

from code_factory.platform.text import stamp_moment

SOON_DAYS = 2
_CHECKBOX = re.compile(r"^\s*[-*] \[([ xX])\]", re.MULTILINE)
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_SECONDS_PER_DAY = 86400
_OFF_BOARD = frozenset({"merged", "released"})


def checklist_counts(description: str) -> tuple[int, int]:
    """`(done, total)` of the `- [ ]` and `* [x]` lines of a description."""
    marks = [found.group(1) for found in _CHECKBOX.finditer(description)]
    return sum(mark != " " for mark in marks), len(marks)


def trim(text: str, limit: int) -> str:
    """The text, or its first `limit - 1` characters and an ellipsis when it is longer."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _day(text: str) -> date | None:
    if not _DAY.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def due_date(due: str) -> str | None:
    """The due text as `YYYY-MM-DD`, or None when it is empty or not a day."""
    day = _day(due)
    return day.isoformat() if day else None


def due_state(due: str, stage: str, now: datetime) -> str:
    """`overdue` before today's UTC day, `soon` from today to two days on, else empty.

    A merged or released ticket is never due.
    """
    day = _day(due)
    if day is None or stage in _OFF_BOARD:
        return ""
    days = (day - now.astimezone(UTC).date()).days
    if days < 0:
        return "overdue"
    return "soon" if days <= SOON_DAYS else ""


def days_in_column(stage_since: str, now: datetime) -> int | None:
    """Whole days since the ticket entered its column, rounded down; None when unknown."""
    since = stamp_moment(stage_since)
    if since is None:
        return None
    return int((now.timestamp() - since) // _SECONDS_PER_DAY)


def budget_amount(text: str) -> float | None:
    """A budget text as dollars; None when it is empty, not a number or not finite."""
    try:
        amount = float(text) if text.strip() else None
    except ValueError:
        return None
    return amount if amount is not None and math.isfinite(amount) else None
