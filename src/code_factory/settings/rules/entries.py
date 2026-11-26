"""The entries of exceptions.toml held to their model."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from code_factory.settings.models.problems import Problem
from code_factory.settings.rules.config import TomlError, parse_toml
from code_factory.settings.rules.lines import entry_line, header_line
from code_factory.settings.rules.tool_files import EXCEPTIONS_FILE

TEXT, DATE, TICKET = "text", "date", "ticket"
MODEL: dict[str, dict[str, str]] = {
    "advisory": {"id": TEXT, "file": TEXT, "reason": TEXT, "ticket": TICKET, "expires": DATE},
    "age": {
        "package": TEXT,
        "lockfile": TEXT,
        "reason": TEXT,
        "chosen": DATE,
        "ticket": TICKET,
        "expires": DATE,
    },
    "quarantine": {"test": TEXT, "reason": TEXT, "ticket": TICKET, "expires": DATE},
}
_NAME_KEY = {"advisory": "id", "age": "package", "quarantine": "test"}


@dataclass(frozen=True)
class ExceptionEntry:
    """An entry that fits its model.

    `name` is the advisory's `id`, the age entry's `package` or the quarantined `test`; `file` its
    `file` or `lockfile` (empty for a test); `at` its place in the file, as `quarantine[0]`.
    """

    kind: str
    at: str
    name: str
    name_line: int
    file: str
    ticket: str
    ticket_line: int
    expires: date
    expires_line: int


def _blank(value: object) -> bool:
    return isinstance(value, str) and not value.strip()


def _field_problem(kind: str, value: object, existing: frozenset[str] | None) -> str | None:
    if kind == DATE:
        return None if type(value) is date else "expected a date"
    if not isinstance(value, str):
        return "expected text"
    if _blank(value):
        return "blank"
    if kind == TICKET and existing is not None and value not in existing:
        return f"no ticket {value}"
    return None


def _entry_problems(
    text: str, list_name: str, index: int, entry: dict[str, Any], existing: frozenset[str] | None
) -> list[Problem]:
    model = MODEL[list_name]
    at = f"{list_name}[{index}]"
    found = []
    for key, value in entry.items():
        why = "unknown field" if key not in model else _field_problem(model[key], value, existing)
        if why is not None:
            line = entry_line(text, list_name, index, key)
            found.append(Problem(EXCEPTIONS_FILE, line, f"{at}.{key}: {why}"))
    header = header_line(text, list_name, index)
    found.extend(
        Problem(EXCEPTIONS_FILE, header, f"{at}.{key}: missing")
        for key in model
        if key not in entry
    )
    return found


def _fitting(text: str, list_name: str, index: int, entry: dict[str, Any]) -> ExceptionEntry:
    def line(key: str) -> int:
        return entry_line(text, list_name, index, key)

    name_key = _NAME_KEY[list_name]
    file_key = "lockfile" if list_name == "age" else "file"
    return ExceptionEntry(
        kind=list_name,
        at=f"{list_name}[{index}]",
        name=entry[name_key],
        name_line=line(name_key),
        file=entry.get(file_key, ""),
        ticket=entry["ticket"],
        ticket_line=line("ticket"),
        expires=entry["expires"],
        expires_line=line("expires"),
    )


def _lists(raw: dict[str, Any], text: str) -> tuple[dict[str, list[dict[str, Any]]], list[Problem]]:
    lists: dict[str, list[dict[str, Any]]] = {}
    problems = []
    for key, value in raw.items():
        if key not in MODEL:
            problems.append(
                Problem(EXCEPTIONS_FILE, header_line(text, key), f"{key}: unknown table")
            )
        elif isinstance(value, list) and all(isinstance(item, dict) for item in value):
            lists[key] = value
        else:
            problems.append(Problem(EXCEPTIONS_FILE, 0, f"{key}: expected a list of tables"))
    return lists, problems


def read_exceptions(
    text: str, existing: frozenset[str] | None
) -> tuple[list[ExceptionEntry], list[Problem]]:
    """The entries that fit the model, and the problems of everything else.

    `existing` holds the tickets that exist; None skips the check that a ticket does.
    """
    raw = parse_toml(text)
    if isinstance(raw, TomlError):
        return [], [Problem(EXCEPTIONS_FILE, raw.line, f"toml: {raw.message}")]
    lists, problems = _lists(raw, text)
    entries = []
    for list_name, items in lists.items():
        for index, item in enumerate(items):
            found = _entry_problems(text, list_name, index, item, existing)
            problems.extend(found)
            if not found:
                entries.append(_fitting(text, list_name, index, item))
    return entries, problems


def exception_tickets(text: str) -> tuple[str, ...]:
    """The tickets the entries name, in file order, to ask whether they exist."""
    raw = parse_toml(text)
    if isinstance(raw, TomlError):
        return ()
    found = []
    for key, items in raw.items():
        if key in MODEL and isinstance(items, list):
            found.extend(
                ticket
                for item in items
                if isinstance(item, dict)
                and isinstance(ticket := item.get("ticket"), str)
                and ticket.strip()
            )
    return tuple(found)
