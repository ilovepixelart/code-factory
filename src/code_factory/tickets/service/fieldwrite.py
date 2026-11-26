"""Writing a ticket's fields and links in one unit of work, for the service and the unit."""

from datetime import datetime
from typing import Any

from code_factory.platform.errors import BadRequestError
from code_factory.tickets.models import NewTicket, Ticket, WrittenFields
from code_factory.tickets.repository import TicketRepository
from code_factory.tickets.rules import clean_fields, ticket_id, ticket_number
from code_factory.tickets.service.common import to_ticket
from code_factory.tickets.tables import LINK_KINDS, TicketRow

FIELD_ORDER = ("title", *WrittenFields.model_fields)


def linked(value: object) -> list[int]:
    """A cleaned link value (`None`, one parent number, or a list of numbers) as a list."""
    if isinstance(value, int):
        return [value]
    if isinstance(value, list):
        return [number for number in value if isinstance(number, int)]
    return []


def link_numbers(ticket: Ticket, kind: str) -> list[int]:
    """The numbers of the tickets the ticket holds as `kind`."""
    ids: object = getattr(ticket, kind)
    names = [ids] if isinstance(ids, str) else ids
    return [ticket_number(i) for i in names if i] if isinstance(names, list) else []


def differs(current: Ticket, name: str, value: object) -> bool:
    """Whether the cleaned `value` is not what the ticket holds in field `name`."""
    if name in LINK_KINDS:
        return link_numbers(current, name) != linked(value)
    return bool(getattr(current, name) != value)


async def read_ticket(tickets: TicketRepository, row: TicketRow) -> Ticket:
    """The ticket the row holds, with its links and pull request."""
    links = await tickets.links_of([row.number])
    pulls = await tickets.pull_requests_of([row.number])
    return to_ticket(row, links[row.number], pulls.get(row.number))


async def link_tickets(
    tickets: TicketRepository,
    number: int,
    links: dict[str, Any],
    held: dict[str, list[int]] | None = None,
) -> None:
    """Replace the ticket's links of each kind in `links`; `BadRequestError` for a bad target.

    Only a target the ticket does not hold already is checked, so an old link to a ticket that
    was deleted since does not stop the list from changing.
    """
    for kind, value in links.items():
        target = linked(value)
        added = [t for t in target if t not in (held or {}).get(kind, [])]
        if number in added:
            msg = f"{ticket_id(number)} cannot name itself as {kind}"
            raise BadRequestError(msg)
        missing = await tickets.missing(added)
        if missing:
            msg = f"{ticket_id(missing[0])} does not exist; name an existing ticket as {kind}"
            raise BadRequestError(msg)
        if kind == "parent" and added and number in await tickets.ancestors(added[0]):
            msg = (
                f"{ticket_id(added[0])} descends from {ticket_id(number)}; a ticket cannot "
                "be under itself"
            )
            raise BadRequestError(msg)
        await tickets.replace_links(number, kind, target)


async def write_fields(
    tickets: TicketRepository, row: TicketRow, cleaned: dict[str, Any], now: datetime
) -> tuple[Ticket, Ticket, list[str]]:
    """Set the cleaned fields that differ; answers the ticket before, after, and the names changed.

    Writes no activity: the caller records what its own use case means by the change.
    """
    current = await read_ticket(tickets, row)
    changed = [
        name for name in FIELD_ORDER if name in cleaned and differs(current, name, cleaned[name])
    ]
    if not changed:
        return current, current, []
    for name in changed:
        if name not in LINK_KINDS:
            setattr(row, name, cleaned[name])
    await tickets.flush(str(cleaned.get("source", "")))
    held = {kind: link_numbers(current, kind) for kind in LINK_KINDS}
    await link_tickets(
        tickets, row.number, {k: cleaned[k] for k in changed if k in LINK_KINDS}, held
    )
    row.updated_at = now
    return current, await read_ticket(tickets, row), changed


async def insert_ticket(
    tickets: TicketRepository, new: NewTicket, now: datetime, extra: dict[str, Any] | None = None
) -> TicketRow:
    """Insert the ticket under the next number and link it; `BadRequestError` when it is refused.

    A `source` is held by one ticket per repository (`ConflictError` for a second). Writes no
    activity.
    """
    cleaned = clean_fields(new)
    if not str(cleaned.get("repository", "")):
        raise BadRequestError("a ticket needs a repository: name the tracked repository")
    links = {kind: cleaned.pop(kind) for kind in LINK_KINDS if kind in cleaned}
    values = {**cleaned, **(extra or {}), "created_at": now, "updated_at": now}
    row = await tickets.insert(values)
    await link_tickets(tickets, row.number, links)
    return row
