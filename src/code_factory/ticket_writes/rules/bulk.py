"""Bulk changes, drops and column limits: choosing, checking and wording."""

from collections.abc import Mapping, Sequence
from typing import Any

from code_factory.ticket_writes.models import PRIORITIES, STAGES, BulkChoice
from code_factory.tickets.models import TicketCore

_ACTIONS = ("stage", "priority", "label", "archived")
ONE_ACTION = "one action and at least one ticket"
LIMIT_REFUSED = "a limit must be a positive whole number"
MAX_LIMIT = 2**31 - 1  # what the `integer` column stores


def _entries(listed: object) -> list[str]:
    if not isinstance(listed, list) or not all(isinstance(entry, str) for entry in listed):
        return []
    return [text for entry in listed if (text := entry.strip())]


def bulk_choice(body: Mapping[str, Any]) -> BulkChoice | str:
    """The one action and the tickets of a bulk body, or the refusal.

    An action given empty still counts as given (`archived: ""` restores).
    """
    given = [name for name in _ACTIONS if name in body]
    tickets = _entries(body.get("tickets"))
    if len(given) != 1 or not tickets:
        return ONE_ACTION
    return BulkChoice(field=given[0], value=str(body[given[0]]).strip(), tickets=tickets)


def check_bulk(field: str, value: str) -> str | None:
    """The refusal for a bulk value that is not one the field takes."""
    if field not in _ACTIONS:
        return ONE_ACTION
    if field == "stage" and value not in STAGES:
        return f"unknown stage {value}"
    if field == "priority" and value and value not in PRIORITIES:
        return f"unknown priority {value}"
    if field == "label" and (not value or "," in value):
        return "a label is one word or phrase"
    if field == "archived" and value not in {"", "true"}:
        return "archived is true or empty"
    return None


def bulk_change(ticket: TicketCore, field: str, value: str) -> tuple[str, str, str]:
    """`(field, new text, old text)` of a bulk priority, label or archive on `ticket`."""
    if field == "label":
        labels = ticket.labels
        wanted = labels if value in labels else [*labels, value]
        return "labels", ", ".join(wanted), ", ".join(labels)
    if field == "archived":
        return "archived", value, "true" if ticket.archived else ""
    return field, value, str(getattr(ticket, field))


def bulk_notice(field: str, value: str, count: int) -> str:
    """The toast of a bulk change: singular for one ticket."""
    many = f"{count} ticket{'' if count == 1 else 's'}"
    if field == "stage":
        return f"Moved {many} to {value.capitalize()}"
    if field == "priority":
        return f"Set {value} priority on {many}"
    if field == "label":
        return f"Labelled {many} {value}"
    return f"Archived {many}" if value == "true" else f"Restored {many}"


def drop_groups(order: Sequence[str]) -> list[tuple[str, list[str]]]:
    """A drop's `repository/id` entries grouped by repository, in first-seen order."""
    groups: dict[str, list[str]] = {}
    for entry in order:
        repository, _, ticket = entry.strip().partition("/")
        groups.setdefault(repository.strip(), []).append(ticket.strip())
    return list(groups.items())


def rank_positions(ids: Sequence[str], ranks: Mapping[str, int]) -> dict[str, int]:
    """The rank each known id changes to: its place in the drop, counted from 1."""
    return {
        ticket: place
        for place, ticket in enumerate(ids, start=1)
        if ticket in ranks and ranks[ticket] != place
    }


def limit_value(raw: object) -> int | str | None:
    """A column limit: `None` clears, a positive whole number sets, anything else is refused."""
    if raw is None:
        return None
    if type(raw) is int and 0 < raw <= MAX_LIMIT:
        return raw
    return LIMIT_REFUSED
