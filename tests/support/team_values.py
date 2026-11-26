"""Builders the team tests share. Times are epoch seconds; NOW is 2026-11-23 12:00:00 UTC."""

from code_factory.team.models import Ask, Lease, TeamAgent, TeamRun

NOW = 1_795_435_200.0
MIDNIGHT = 1_795_392_000.0  # 00:00 UTC of the day NOW falls in
DAY = 86_400.0


def run(
    id: str = "r1",  # noqa: A002
    ticket: str = "CF-1",
    agent: str = "",
    started: float = NOW - 100,
    **fields: object,
) -> TeamRun:
    """A build run, running unless an `exit_code` is given."""
    fields = {"stage": "build"} | fields
    return TeamRun(id=id, ticket_id=ticket, agent=agent, started_at=started, **fields)  # ty: ignore[invalid-argument-type]


def ended(
    id: str = "r1",  # noqa: A002
    ticket: str = "CF-1",
    agent: str = "",
    started: float = NOW - 100,
    seconds: float = 50,
    **fields: object,
) -> TeamRun:
    """A run that exited 0 (unless `exit_code` says otherwise) `seconds` after it started."""
    fields = {"exit_code": 0} | fields
    return run(id, ticket, agent, started=started, ended_at=started + seconds, **fields)


def agent(name: str, *roles: str, **fields: object) -> TeamAgent:
    """A defined agent working `roles`."""
    return TeamAgent(name=name, roles=roles, **fields)  # ty: ignore[invalid-argument-type]


def lease(who: str = "writer", runs: tuple[str, ...] = (), beat_ago: float = 0.0) -> Lease:
    """A claim made at NOW - beat_ago and last beaten then."""
    return Lease(agent=who, runs=runs, claimed_at=NOW - beat_ago, beat_at=NOW - beat_ago)


def ask(
    *runs: TeamRun, key: str = "CF-1", stage: str = "build", now: float = NOW, **fields: object
) -> Ask:
    """What a pick reads, over `runs`."""
    return Ask(key=key, stage=stage, runs=tuple(runs), now=now, **fields)  # ty: ignore[invalid-argument-type]
