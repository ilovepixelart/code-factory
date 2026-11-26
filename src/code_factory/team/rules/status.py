"""What each agent is doing, how its latest run ended, and its runs of a window."""

from collections.abc import Mapping, Sequence

from code_factory.team.models import (
    Ask,
    Chain,
    Doing,
    Lane,
    LaneRun,
    Last,
    Lease,
    Outcome,
    TeamAgent,
    TeamRun,
)
from code_factory.team.rules.caps import at_cap, over_cap, usage
from code_factory.team.rules.claims import LEASE_SECONDS, holds
from code_factory.team.rules.pick import STOPPED


def _latest(runs: Sequence[TeamRun]) -> TeamRun | None:
    """The run that started last; the later of two that started together."""
    return max(enumerate(runs), key=lambda item: (item[1].started_at, item[0]))[1] if runs else None


def outcome(agent: TeamAgent, run: TeamRun, runs: Sequence[TeamRun]) -> Outcome:
    """How a run ended, in a word; "over" is the ticket's cap evaluated at the run's end."""
    if run.exit_code is None:
        return "running"
    if run.limited_until is not None:
        return "usage limit"
    when = run.started_at if run.ended_at is None else run.ended_at
    ask = Ask(key=run.ticket_id, stage=run.stage, runs=tuple(runs), now=when)
    over = over_cap(agent, ask) is not None
    if run.exit_code == 0:
        if run.uncommitted:
            return "uncommitted, over limit" if over else "uncommitted"
        return "finished, over limit" if over else "finished"
    if over:
        return "over limit"
    return "stopped" if run.exit_code == STOPPED else "failed"


def _over_limit(agent: TeamAgent, runs: Sequence[TeamRun], now: float) -> Doing | None:
    latest = _latest([run for run in runs if run.agent == agent.name])
    if latest is None:
        return None
    ask = Ask(key=latest.ticket_id, stage=latest.stage, runs=tuple(runs), now=now)
    if at_cap(agent, ask) is None:
        return None
    return Doing(state="over limit", repository=latest.repository, id=latest.ticket_id)


def doing(
    agents: Sequence[TeamAgent],
    leases: Mapping[str, Lease],
    runs: Sequence[TeamRun],
    now: float,
    repositories: Mapping[str, str],
) -> dict[str, Doing]:
    """What each defined agent that is not idle is doing, by name.

    Its claim that holds: working while its heartbeat is fresh, else waiting, with its usage;
    else the ticket of its latest run when that ticket is at a cap. `repositories` names the
    repository of each claimed ticket.
    """
    found: dict[str, Doing] = {}
    for agent in agents:
        held = next(
            (
                (key, lease)
                for key, lease in leases.items()
                if lease.agent == agent.name and holds(lease, runs, now)
            ),
            None,
        )
        if held is None:
            state = _over_limit(agent, runs, now)
        else:
            key, lease = held
            fresh = now - lease.beat_at < LEASE_SECONDS
            ask = Ask(key=key, runs=tuple(runs), now=now)
            state = Doing(
                state="working" if fresh else "waiting",
                repository=repositories.get(key, ""),
                id=key,
                usage=usage(agent, ask),
            )
        if state is not None:
            found[agent.name] = state
    return found


def last(
    agents: Sequence[TeamAgent], runs: Sequence[TeamRun], repositories: Mapping[str, str]
) -> dict[str, Last]:
    """Each defined agent's latest run by its start; an agent without runs is absent."""
    found: dict[str, Last] = {}
    for agent in agents:
        latest = _latest([run for run in runs if run.agent == agent.name])
        if latest is None:
            continue
        found[agent.name] = Last(
            run=latest.id,
            repository=latest.repository or repositories.get(latest.ticket_id, ""),
            id=latest.ticket_id,
            stage=latest.stage,
            at=latest.started_at if latest.ended_at is None else latest.ended_at,
            outcome=outcome(agent, latest, runs),
            until=latest.limited_until,
            refused=latest.resume_refused,
            context_at=latest.context_at,
        )
    return found


def _lane_runs(agent: TeamAgent, runs: Sequence[TeamRun], since: float) -> tuple[LaneRun, ...]:
    shown = sorted(
        (
            run
            for run in runs
            if run.agent == agent.name and (run.started_at > since or run.ended_at is None)
        ),
        key=lambda run: run.started_at,
    )
    return tuple(
        LaneRun(
            id=run.id,
            repository=run.repository,
            ticket=run.ticket_id,
            stage=run.stage,
            started_at=run.started_at,
            ended_at=run.ended_at,
            outcome=outcome(agent, run, runs),
        )
        for run in shown
    )


def lanes(
    agents: Sequence[TeamAgent],
    runs: Sequence[TeamRun],
    leases: Mapping[str, Lease],
    window: tuple[float, float],
    repositories: Mapping[str, str],
) -> tuple[Lane, ...]:
    """A lane per agent in roster order, then `default` for runs of no agent when one falls in.

    A lane's runs are those started after `since` (the window's start, then its end `now`) or
    still running, by their start.
    """
    since, now = window
    now_doing = doing(agents, leases, runs, now, repositories)
    found = [
        Lane(agent=agent.name, doing=now_doing.get(agent.name), runs=_lane_runs(agent, runs, since))
        for agent in agents
    ]
    unnamed = _lane_runs(TeamAgent(name=""), runs, since)  # no definition, so no caps
    if unnamed:
        found.append(Lane(agent="default", doing=None, runs=unnamed))
    return tuple(found)


def chains(lanes_: Sequence[Lane]) -> tuple[Chain, ...]:
    """A chain per ticket with a run in `lanes_`, ordered by the ticket's first start.

    `waited` holds the seconds between each run's end and the next run's start: 0 when they
    overlap, `None` while the earlier run still runs.
    """
    runs = sorted(
        (run for lane in lanes_ for run in lane.runs if run.ticket),
        key=lambda run: (run.started_at, run.id),
    )
    ids: dict[tuple[str, str], list[str]] = {}
    waits: dict[tuple[str, str], list[float | None]] = {}
    ends: dict[tuple[str, str], float | None] = {}
    for run in runs:
        place = (run.repository, run.ticket)
        if place in ids:
            before = ends[place]
            waits[place].append(None if before is None else max(run.started_at - before, 0.0))
            ids[place].append(run.id)
        else:
            ids[place] = [run.id]
            waits[place] = []
        ends[place] = run.ended_at
    return tuple(
        Chain(
            repository=place[0], ticket=place[1], runs=tuple(ids[place]), waited=tuple(waits[place])
        )
        for place in ids
    )
