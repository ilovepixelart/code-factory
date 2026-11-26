"""The checks on an entry's fields, in the order its refusals are reported."""

from code_factory.memory.models import MemoryFields
from code_factory.memory_extras.rules.constants import KINDS
from code_factory.memory_extras.rules.scope import scope_refusal
from code_factory.platform.text import is_iso_date

ONE_LINE = "why, source, guard, verdict, scope, supersedes and cites are one line each"


def check_fields(kind: str, statement: str, fields: MemoryFields, verdict: str = "") -> str | None:
    """The sentence naming why the entry cannot be written as it is, or None."""
    if kind not in KINDS:
        return "kind must be one of rule, decision, lesson"
    if not statement.strip():
        return "an entry needs a statement"
    lines = (fields.why, fields.source, fields.guard, verdict, fields.scope)
    if any("\n" in line for line in (*lines, *fields.supersedes, *fields.cites)):
        return ONE_LINE
    if fields.expires.strip() and not _is_day(fields.expires.strip()):
        return "expires is a date, YYYY-MM-DD"
    if fields.until and not is_ticket_id(fields.until):
        return "until names one ticket id"
    return scope_refusal(fields)


def is_ticket_id(text: str) -> bool:
    """Whether the text is `CF-<n>`, the id of a ticket, n from 1."""
    digits = text.removeprefix("CF-")
    return digits != text and digits.isascii() and digits.isdigit() and int(digits) > 0


def _is_day(text: str) -> bool:
    return len(text) == len("YYYY-MM-DD") and text[4] == text[7] == "-" and is_iso_date(text)
