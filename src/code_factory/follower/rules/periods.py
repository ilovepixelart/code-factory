"""Calendar periods, retry waits and transient failures."""

import re
from datetime import UTC, datetime, timedelta

LAST_LINES = 40
_TRANSIENT = re.compile(
    r"overloaded|rate[ _-]?limit|(api error|http|status)\W*(429|5\d\d)\b|timed out|econnreset"
    r"|connection reset",
    re.IGNORECASE,
)


def period(every: str, moment: datetime) -> str:
    """The UTC period `moment` falls in: `2026-09-21`, `2026-W39` or `2026-09`; '' otherwise."""
    at = moment.astimezone(UTC)
    if every == "day":
        return at.strftime("%Y-%m-%d")
    if every == "week":
        year, week, _ = at.isocalendar()
        return f"{year}-W{week:02d}"
    if every == "month":
        return at.strftime("%Y-%m")
    return ""


def retry_wait(attempt: int) -> timedelta:
    """How long after its end a failed run is tried again: 10 s doubling, at most 300 s."""
    return timedelta(seconds=min(10 * 2 ** (attempt - 1), 300))


def transient(log: str) -> bool:
    """Whether the last lines of a log show a failure worth trying again."""
    tail = "\n".join(log.splitlines()[-LAST_LINES:])
    return _TRANSIENT.search(tail) is not None
