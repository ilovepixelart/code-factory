"""F1: the range of a read, from epoch seconds, a UTC date or an RFC 3339 instant."""

import re
from datetime import UTC, datetime

from code_factory.factory.models import Period
from code_factory.platform.errors import BadRequestError

DAY_S = 86400.0
DEFAULT_DAYS = 30
MAX_DAYS = 366
DATE_LENGTH = len("2026-11-01")
_EPOCH = re.compile(r"\d+(\.\d+)?")


def _instant(value: str | float, name: str) -> float:
    """`value` as epoch seconds; anything that is not a representable instant is refused."""
    refusal = BadRequestError(f"{name} is not a date or a time")
    try:
        if isinstance(value, str):
            text = value.strip().upper()  # RFC 3339 allows `t` and `z`
            if _EPOCH.fullmatch(text):
                seconds = float(text)
            else:
                if len(text) > DATE_LENGTH and text[DATE_LENGTH] not in "T ":
                    raise refusal  # fromisoformat takes any one character as the separator
                parsed = datetime.fromisoformat(text)
                seconds = (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).timestamp()
        else:
            seconds = float(value)
        datetime.fromtimestamp(seconds, UTC)
    except ValueError, OverflowError, OSError:
        raise refusal from None
    return seconds


def period(from_: str | float | None, to: str | float | None, now: float) -> Period:
    """The half open range `[from_, to)`: to defaults to `now`, from to 30 days before `to`."""
    end = now if to is None else _instant(to, "to")
    start = end - DEFAULT_DAYS * DAY_S if from_ is None else _instant(from_, "from")
    if start >= end:
        msg = "from must be before to"
        raise BadRequestError(msg)
    if end - start > MAX_DAYS * DAY_S:
        msg = f"a range is at most {MAX_DAYS} days"
        raise BadRequestError(msg)
    return Period(from_=start, to=end, now=now)
