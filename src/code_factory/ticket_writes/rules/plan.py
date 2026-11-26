"""What a create or an update writes, and the order in which it is refused.

The order is the previous store's: line breaks, type, stage, card fields, branch, budget,
parallel, then links. Every sentence is the one the app shows.
"""

from collections.abc import Callable, Collection, Mapping
from typing import Any

from code_factory.ticket_writes.models import (
    CARD_FIELDS,
    DEFAULT_TYPE,
    EDITABLE,
    LINK_FIELDS,
    LIST_FIELDS,
    STAGES,
    TYPES,
    CreatePlan,
    Record,
    UpdatePlan,
)
from code_factory.ticket_writes.rules.fields import (
    BUDGET_REFUSED,
    PARALLEL_REFUSED,
    budget_text,
    card_fields,
    normalised_list,
    one_line,
    parallel_text,
    unknown_fields,
)
from code_factory.ticket_writes.rules.links import check_links
from code_factory.tickets.models import LinkGraph, NewTicket, TicketCore

BranchRefusal = Callable[[str], str | None]
NO_TITLE = "a ticket needs a title"
_SPECIAL = {"stage", "archived"}


def held_text(ticket: TicketCore, name: str) -> str:
    """A field as the app shows it: lists joined by `, `, `archived` `true` or empty."""
    value: object = getattr(ticket, name)
    if name == "archived":
        return "true" if value else ""
    if isinstance(value, list):
        return ", ".join(str(part) for part in value)
    return str(value)


def written_fields(values: Mapping[str, str]) -> dict[str, Any]:
    """Field text as the tickets module takes it: the comma lists become lists."""
    return {
        name: [part for part in value.split(", ") if part] if name in LIST_FIELDS else value
        for name, value in values.items()
    }


def _list(text: str) -> list[str]:
    return [part for part in text.split(", ") if part]


def _values(fields: Mapping[str, str], refuse_branch: BranchRefusal, held_branch: str) -> Any:  # noqa: ANN401  # the values or a refusal sentence
    kind = fields.get("type")
    if kind is not None and kind.strip() not in TYPES:
        return f"unknown type {kind.strip()}"
    stage = fields.get("stage", "").strip()
    if stage and stage not in STAGES:
        return f"unknown stage {stage}"
    card = card_fields({name: fields[name] for name in CARD_FIELDS if name in fields})
    if isinstance(card, str):
        return card
    values = {name: card.get(name, raw.strip()) for name, raw in fields.items()}
    branch = values.get("branch", "")
    why = refuse_branch(branch) if branch and branch != held_branch else None
    if why is not None:
        return f"bad branch {branch}: {why}"
    for name, rule, refusal in (
        ("budget", budget_text, BUDGET_REFUSED),
        ("parallel", parallel_text, PARALLEL_REFUSED),
    ):
        if name in values:
            values[name] = rule(values[name])
            if values[name] == refusal:
                return refusal
    for name in ("blocked_by", "caused_by"):
        if name in values:
            values[name] = ", ".join(dict.fromkeys(_list(normalised_list(values[name]))))
    return values


def _wanted(values: Mapping[str, str]) -> dict[str, list[str]]:
    return {
        name: [values[name]] if name == "parent" and values[name] else _list(values[name])
        for name in LINK_FIELDS
        if name in values
    }


def plan_create(
    repository: str,
    fields: Mapping[str, str],
    graph: LinkGraph,
    refuse_branch: BranchRefusal,
) -> CreatePlan | str:
    """The ticket to file, its branch and archived flag and its records, or the refusal.

    A blank title is left to the tickets module; every link counts as added.
    """
    refused = one_line(fields.items())
    if refused is not None:
        return refused
    given = {name: value for name, value in fields.items() if name != "type" or value.strip()}
    values = _values(given, refuse_branch, "")
    if isinstance(values, str):
        return values
    refused = check_links(None, _wanted(values), {}, graph)
    if refused is not None:
        return refused
    kind = values.get("type", DEFAULT_TYPE)
    written = written_fields({n: v for n, v in values.items() if n not in _SPECIAL | {"branch"}})
    ticket = NewTicket.model_validate(
        {"title": "", **written, "repository": repository, "type": kind}
    )
    return CreatePlan(
        ticket=ticket,
        branch=values.get("branch", ""),
        archived=values.get("archived") == "true",
        activity=[Record(kind="created", data={"type": kind})],
    )


def _current_links(current: TicketCore) -> dict[str, list[str]]:
    return {
        "parent": [current.parent] if current.parent else [],
        "blocked_by": list(current.blocked_by),
        "caused_by": list(current.caused_by),
    }


def plan_update(
    current: TicketCore,
    patch: Mapping[str, str],
    graph: LinkGraph,
    refuse_branch: BranchRefusal,
) -> UpdatePlan | str:
    """What the edit writes, or the refusal.

    Records come in the order the names were given, one `field` each (a description records an
    empty value), then `archived` or `restored`; the column change is recorded by whoever makes it.
    """
    refused = unknown_fields(patch, EDITABLE) or one_line(patch.items())
    if refused is not None:
        return refused
    if "title" in patch and not patch["title"].strip():
        return NO_TITLE
    values = _values(patch, refuse_branch, current.branch)
    if isinstance(values, str):
        return values
    refused = check_links(current.id, _wanted(values), _current_links(current), graph)
    if refused is not None:
        return refused
    changed = {n: v for n, v in values.items() if n != "stage" and v != held_text(current, n)}
    flag = changed.pop("archived", None)
    activity = [
        Record(kind="field", data={"name": n, "value": "" if n == "description" else v})
        for n, v in changed.items()
    ]
    archived = None if flag is None else flag == "true"
    if archived is not None:
        activity.append(Record(kind="archived" if archived else "restored"))
    return UpdatePlan(
        values=changed, stage=values.get("stage", ""), archived=archived, activity=activity
    )


def branch_missing(
    name: str, local: Collection[str], remote: Collection[str], default: str
) -> str | None:
    """The refusal for a branch no ref holds.

    The column is read from the branch, so a name that does not exist would change nothing a
    reader sees.
    """
    if name in local or name in remote:
        return None
    return (
        f"no branch {name} exists, so the ticket would stay in Spec: code-factory start <ID> "
        f"or a Build run makes the ticket's branch from {default}; set branch once it exists"
    )


def with_question(description: str, question: str) -> str:
    """The description with the duplicate question after it, a blank line between."""
    held = description.strip()
    return f"{description.rstrip()}\n\n{question}" if held else question
