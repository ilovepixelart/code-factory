"""Moments as text: UTC stamps, ISO dates and the short day and minute form."""

import re
from datetime import UTC, date, datetime, timedelta

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# ASCII digits only: `\d` would take every script's digits.
_STAMP = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SECONDS_A_DAY = 86400
_ORDINAL_OF_EPOCH = 719163
_LAST_MINUTE_SECOND = 61


def _utc(moment: float | datetime) -> datetime:
    try:
        if isinstance(moment, datetime):
            return moment.astimezone(UTC)
        return datetime.fromtimestamp(moment, UTC)
    except (OverflowError, OSError) as error:
        raise ValueError(f"moment {moment} is outside the years 1 to 9999") from error


def stamp(moment: float | datetime) -> str:
    """The UTC `YYYY-MM-DDTHH:MM:SSZ` of a moment; the fraction of a second is dropped.

    A float is rounded to the microsecond (half to even) first, as `datetime.fromtimestamp` does.

    Raises:
        ValueError: The moment is outside the years 1 to 9999.
    """
    when = _utc(moment)
    return (
        f"{when.year:04d}-{when.month:02d}-{when.day:02d}"
        f"T{when.hour:02d}:{when.minute:02d}:{when.second:02d}Z"
    )


def stamp_moment(text: str) -> float | None:
    """Seconds since the epoch of a stamp in exactly the shape `stamp` writes, else None.

    A second of 60 or 61 (a leap second) is accepted.
    """
    found = _STAMP.fullmatch(text)
    if found is None:
        return None
    year, month, day, hour, minute, second = (int(part) for part in found.groups())
    if second > _LAST_MINUTE_SECOND:
        return None
    try:
        base = datetime(year, month, day, hour, minute, tzinfo=UTC)
    except ValueError:
        return None
    return (base - _EPOCH).total_seconds() + second


def epoch_day(moment: float | datetime) -> int:
    """The UTC day of a moment as `date.toordinal()` (days since 0001-01-00)."""
    if isinstance(moment, datetime):
        return moment.astimezone(UTC).toordinal()
    return int(moment // _SECONDS_A_DAY) + _ORDINAL_OF_EPOCH


def day_text(days: int) -> str:
    """The ISO date of an ordinal day."""
    return date.fromordinal(days).isoformat()


def iso_date_days(text: str) -> int | None:
    """The ordinal day of an ISO date as Python reads one, else None.

    Python accepts `YYYY-MM-DD`, `YYYYMMDD` and the week forms, and ignores text after a complete
    date of length 7, 8 or 10.
    """
    try:
        return date.fromisoformat(text).toordinal()
    except ValueError:
        return None


def is_iso_date(text: str) -> bool:
    """Whether `iso_date_days` reads the text."""
    return iso_date_days(text) is not None


def day_minute(seconds: int) -> str:
    """The UTC `21 Sep 14:30` of an epoch second: day unpadded, English month, no locale."""
    when = _EPOCH + timedelta(seconds=seconds)
    return f"{when.day} {MONTHS[when.month - 1]} {when.hour:02d}:{when.minute:02d}"
