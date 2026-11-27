"""Rules on single field values: the sentences are the ones the app shows."""

import re
from collections.abc import Collection, Iterable, Mapping
from decimal import Decimal, InvalidOperation

from code_factory.platform.text import is_iso_date, quoted_list
from code_factory.ticket_writes.models import PRIORITIES

_LINE_BREAKS = frozenset("\n\r\v\f\x85") | {chr(0x2028), chr(0x2029)}
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)
_DIGITS = re.compile(r"\d+", re.ASCII)
_ARCHIVED = {"": "", "false": "", "true": "true", "on": "true"}
BUDGET_REFUSED = "budget must be a number of dollars"
PARALLEL_REFUSED = "parallel must be 1 to 4"
_MAX_PARALLEL = 4
# Bounds the plain form of a budget: `1e-999999999999` would otherwise be written out in full.
_MAX_MAGNITUDE = 30


def unknown_fields(names: Iterable[str], known: Collection[str]) -> str | None:
    """The refusal naming the names outside `known`, sorted and once each."""
    unknown = sorted({name for name in names if name not in known})
    return f"unknown fields {quoted_list(unknown)}" if unknown else None


def one_line(fields: Iterable[tuple[str, str]]) -> str | None:
    """The refusal for the first field but `description` that holds a line break."""
    for name, value in fields:
        if name != "description" and any(char in _LINE_BREAKS for char in value):
            return f"{name} holds a line break"
    return None


def normalised_list(text: str) -> str:
    """The comma list with each entry stripped, empty entries dropped, joined by `, `."""
    return ", ".join(part for raw in text.split(",") if (part := raw.strip()))


def _archived(text: str) -> str | None:
    return _ARCHIVED.get(text.strip().lower())


def card_fields(values: Mapping[str, str]) -> dict[str, str] | str:
    """The card fields given, normalised, or the first refusal (priority, due, archived)."""
    out: dict[str, str] = {}
    for name, raw in values.items():
        text = raw.strip()
        if name == "labels":
            text = normalised_list(raw)
        out[name] = text
    priority = out.get("priority", "")
    if priority and priority not in PRIORITIES:
        return f"unknown priority {priority}"
    due = out.get("due", "")
    if due and not is_iso_date(due):
        return f"bad due date {due}"
    if "archived" in out:
        flag = _archived(out["archived"])
        if flag is None:
            return f"bad archived {out['archived'].strip()}"
        out["archived"] = flag
    return out


def budget_text(text: str) -> str:
    """The budget as a plain decimal, empty to clear, or the refusal.

    Only ASCII decimal text is read: Python's own `float` also takes `1_0` and other scripts'
    digits, which the board never did.
    """
    trimmed = text.strip()
    if not trimmed:
        return ""
    if not _NUMBER.fullmatch(trimmed):
        return BUDGET_REFUSED
    try:
        value = Decimal(trimmed)
        exponent = int(value.as_tuple().exponent)
        if value < 0 or abs(value.adjusted()) > _MAX_MAGNITUDE or -exponent > _MAX_MAGNITUDE:
            return BUDGET_REFUSED
    except InvalidOperation, OverflowError:
        return BUDGET_REFUSED
    return format(abs(value) if value.is_zero() else value, "f")


def parallel_text(text: str) -> str:
    """The attempts to run side by side, 1 to 4 (empty to clear), or the refusal."""
    trimmed = text.strip()
    if not trimmed:
        return ""
    if not _DIGITS.fullmatch(trimmed):
        return PARALLEL_REFUSED
    count = trimmed.lstrip("0")  # compared as text: converting thousands of digits is refused
    return count if count in {str(n) for n in range(1, _MAX_PARALLEL + 1)} else PARALLEL_REFUSED
