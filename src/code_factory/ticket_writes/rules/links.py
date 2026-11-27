"""Link rules: what an edit may add, and the four kinds of link the app adds and removes."""

from collections.abc import Mapping

from code_factory.ticket_writes.models import LINK_FIELDS, LINK_KINDS, LinkChange
from code_factory.tickets.models import LinkGraph, TicketCore

_HELD_BY_OTHER = ("child", "blocks")


def _loops(own: str, parent: str, graph: LinkGraph) -> bool:
    seen: set[str] = set()
    node: str | None = parent
    while node is not None and node not in seen:
        if node == own:
            return True
        seen.add(node)
        node = graph.parent_of.get(node)
    return False


def check_links(
    own: str | None,
    wanted: Mapping[str, list[str]],
    held: Mapping[str, list[str]],
    graph: LinkGraph,
) -> str | None:
    """The refusal for a link the write adds or changes; links already held are not checked.

    An old link naming a deleted ticket must not freeze the card. `own` is `None` for a ticket
    not yet filed, which cannot name itself nor sit in a loop.
    """
    for kind in LINK_FIELDS:
        added = [t for t in wanted.get(kind, []) if t not in held.get(kind, [])]
        for target in added:
            if target == own:
                return f"{own} cannot link to itself"
            if target not in graph.ids:
                return f"no ticket {target}"
        if kind == "parent" and added and own is not None and _loops(own, added[0], graph):
            return f"parent {added[0]} would make a loop"
    return None


def _held(ticket: TicketCore, field: str) -> list[str]:
    if field == "parent":
        return [ticket.parent] if ticket.parent else []
    return list(ticket.blocked_by)


def _link_value(field: str, held: list[str], linked: str, *, add: bool) -> str | None:
    """The field text after the link is added or removed, `None` when a removal finds none."""
    if add:
        wanted = [linked] if field == "parent" else [*held, *([] if linked in held else [linked])]
    elif linked not in held:
        return None
    else:
        wanted = [] if field == "parent" else [t for t in held if t != linked]
    return ", ".join(wanted)


def link_change(
    own: TicketCore, other: TicketCore | None, kind: str, target: str, *, add: bool
) -> LinkChange | str:
    """The write that adds or removes one link, or the refusal.

    `other` is the ticket `target` names, `None` when there is none. `child` and `blocks` write
    the other ticket's field, so a missing one is refused here; for the other kinds the link
    check of the edit refuses a missing target.
    """
    if kind not in LINK_KINDS:
        return f"unknown link kind {kind}"
    by_other = kind in _HELD_BY_OTHER
    if by_other and other is None:
        return f"no ticket {target}"
    holder = other if by_other and other is not None else own
    field = "parent" if kind in {"parent", "child"} else "blocked_by"
    linked = own.id if by_other else target
    held = _held(holder, field)
    value = _link_value(field, held, linked, add=add)
    if value is None:
        return f"{target} is not linked to {own.id} that way"
    return LinkChange(holder=holder.id, field=field, value=value)
