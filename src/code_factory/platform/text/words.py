"""Small rules on words and numbers every module shares."""

from collections.abc import Iterable

_MINUTE = 60
_HOUR = 3600
_DAY = 86400
_HALF_MINUTE = 30


def one_line(text: str) -> str:
    """The text on one line: runs of whitespace (any Unicode space) become one space."""
    return " ".join(text.split())


def _minutes(seconds: int) -> str:
    whole, rest = divmod(seconds, _MINUTE)
    if rest > _HALF_MINUTE or (rest == _HALF_MINUTE and whole % 2 == 1):
        whole += 1
    return f"{whole}m"


def _one_decimal(value: float, unit: str) -> str:
    return f"{value:.1f}".removesuffix(".0") + unit


def span(seconds: int) -> str:
    """A length of time as `29s`, `2m`, `1.5h` or `10.2d`.

    Minutes round half to even on the second; hours and days keep one decimal, a trailing `.0`
    dropped.
    """
    if seconds < _MINUTE:
        return f"{seconds}s"
    if seconds < _HOUR:
        return _minutes(seconds)
    if seconds < _DAY:
        return _one_decimal(seconds / _HOUR, "h")
    return _one_decimal(seconds / _DAY, "d")


def scalar_text(value: object) -> str | None:
    """`str(value)` for a string, bool, int, float or None; None for anything else."""
    if value is None or isinstance(value, str | bool | int | float):
        return str(value)
    return None


def quoted_list(items: Iterable[str]) -> str:
    """The list as the refusal messages show it: `['a', "it's"]`."""
    return repr(list(items))
