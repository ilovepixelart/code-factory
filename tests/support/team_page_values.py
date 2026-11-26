"""Builders for the Team page tests: hand-written facts, as the previous implementation's tests."""

from typing import Any

from code_factory.team.models import (
    Actor,
    Cycle,
    Facts,
    OwnerItem,
    Row,
    TeamActivity,
    TicketFacts,
    TicketRef,
    Worker,
)

NOW = 1_794_312_000.0
TODAY = 1_794_268_800.0  # 00:00 UTC of the day NOW falls in
MINUTE = 60.0
HOUR = 3600.0
DAY = 86_400.0
PULL = "https://example.test/pull/"


def activity(at: float, kind: str, **data: Any) -> TeamActivity:  # noqa: ANN401
    """A record of a ticket's history; its words are its kind unless `words` is given."""
    words = data.pop("words", kind)
    return TeamActivity(at=at, kind=kind, data=data, words=words)


def reference(id_: str, repository: str = "sample") -> TicketRef:
    """A ticket as a row names it."""
    return TicketRef(repository=repository, id=id_, title=f"Title of {id_}")


def ticket(id_: str, column: str, **fields: Any) -> TicketFacts:  # noqa: ANN401
    """A feature ticket in `column`."""
    return TicketFacts(reference=reference(id_), kind="feature", column=column, **fields)


def worker(
    id_: str,
    kind: str,
    name: str,
    line: str,
    since: float,
    **fields: Any,  # noqa: ANN401
) -> Worker:
    """A live worker on a ticket, last heard from now."""
    values: dict[str, Any] = {
        "key": f"{kind}:{name}:{id_}",
        "repository": "sample",
        "ticket": id_,
        "actor": Actor(kind=kind, name=name),  # ty: ignore[invalid-argument-type]
        "line": line,
        "since": since,
        "last_event": NOW,
        "alive": True,
        "stale_after": 600.0,
    }
    return Worker(**(values | fields))


def owner(id_: str, kind: str, reason: str, since: float, count: int = 1) -> OwnerItem:
    """An inbox item waiting on the owner."""
    return OwnerItem(ticket=reference(id_), kind=kind, reason=reason, since=since, count=count)


def facts(
    tickets: list[TicketFacts] | None = None,
    workers: list[Worker] | None = None,
    owners: list[OwnerItem] | None = None,
    **fields: Any,  # noqa: ANN401
) -> Facts:
    """What one read gathered, with the agents builder and writer."""
    values: dict[str, Any] = {
        "now": NOW,
        "today": TODAY,
        "cycle": Cycle(since=NOW - 7 * DAY, from_="the last 7 days"),
        "tickets": tuple(tickets or ()),
        "workers": tuple(workers or ()),
        "owner": tuple(owners or ()),
        "agents": ("builder", "writer"),
        "paused": (),
    }
    return Facts(**(values | fields))


def ids(rows: tuple[Row, ...]) -> list[str]:
    """The ticket id of each row; empty for a row on no ticket."""
    return [row.ticket.id if row.ticket else "" for row in rows]
