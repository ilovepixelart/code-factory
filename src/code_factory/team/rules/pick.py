"""Which defined agent takes a ticket, and why none does."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from code_factory.team.models import Ask, TeamAgent, TeamRun
from code_factory.team.rules.caps import at_cap

STOPPED = -15
NO_REVIEWER = "no reviewer that did not write the code"
NO_READER = "no reader that did not write the documents"
NO_OTHER_MODEL = "no reviewer on another model than the code's"
NO_AGENT = "no agent for this column"
NO_MATCH = "no agent of this column takes this ticket's type and labels"
_COLUMNS = {"spec": "Spec", "build": "Build", "review": "Review", "merged": "Merged"}


class NoAgent(Exception):  # noqa: N818  # a sentence for the person: why no agent takes it
    """No agent takes the ticket; `str(error)` says why."""


def column_label(stage: str) -> str:
    """A stage's name on the board; any other name reads as `Released`."""
    return _COLUMNS.get(stage, "Released")


def judging(stage: str) -> tuple[str, str | None]:
    """The column whose agents a run of `stage` takes, and the stage whose writers it must not be.

    A review, and each review role, judges the Build and a read the Spec, from the review and spec
    columns.
    """
    if stage in {"review", "critique", "qa", "security", "tests"}:
        return "review", "build"
    if stage == "read":
        return "spec", "spec"
    return stage, None


def takes(agent: TeamAgent, kind: str, labels: str) -> bool:
    """Whether the agent's type and label lists admit a ticket: each list set must match."""
    typed = not agent.types or kind in agent.types
    have = [label.strip() for label in labels.split(",")]
    return typed and (not agent.labels or any(label in agent.labels for label in have))


def _latest(runs: Sequence[TeamRun]) -> TeamRun | None:
    """The run that started last; the later of two that started together."""
    return max(enumerate(runs), key=lambda item: (item[1].started_at, item[0]))[1] if runs else None


def _here(ask: Ask) -> list[TeamRun]:
    return [run for run in ask.runs if run.stage == ask.stage and run.ticket_id == ask.key]


def waits_out_limit(agent: TeamAgent, ask: Ask) -> bool:
    """Whether the agent's latest run on any ticket ended on a usage limit that has not reset."""
    latest = _latest([run for run in ask.runs if run.agent == agent.name])
    return latest is not None and (latest.limited_until or 0.0) > ask.now


def failed_here(agent: TeamAgent, ask: Ask) -> str | None:
    """Why the agent failed the ticket at the ask's stage, by its latest unrecovered run there."""
    here = _here(ask)
    latest = _latest([run for run in here if run.agent == agent.name])
    if latest is None:
        return None
    column = column_label(ask.stage)
    if latest.exit_code == 0 and latest.halted.startswith("no progress"):
        return f"{agent.name} made no progress on this ticket at {column}"
    code = latest.exit_code
    if code is None or code in {0, STOPPED} or latest.limited_until is not None:
        return None
    if any(run.started_at > latest.started_at and run.exit_code == 0 for run in here):
        return None
    return f"{agent.name} failed this ticket at {column} (exit {code})"


def unable(agent: TeamAgent, ask: Ask) -> str | None:
    """Why the agent, though it works the column, cannot take a run now; `None` when it can."""
    if waits_out_limit(agent, ask):
        return f"{agent.name} waits out a usage limit"
    if agent.refusal:
        return agent.refusal
    return failed_here(agent, ask) if ask.escalate else None


def _judged(column: Sequence[TeamAgent], ask: Ask) -> Ask:
    """The ask without escalation when every agent of the column failed the ticket there."""
    every = ask.escalate and all(failed_here(agent, ask) is not None for agent in column)
    return replace(ask, escalate=ask.escalate and not every)


def _column(agents: Sequence[TeamAgent], ask: Ask) -> tuple[list[TeamAgent], list[TeamAgent]]:
    """The agents working the stage's column, and those of them that take the ticket."""
    role = judging(ask.stage)[0]
    worked = [agent for agent in agents if role in agent.roles]
    return worked, [agent for agent in worked if takes(agent, ask.kind, ask.labels)]


def _writers(ask: Ask) -> list[str]:
    judged = judging(ask.stage)[1]
    if judged is None:
        return []
    return [run.agent for run in ask.runs if run.stage == judged and run.ticket_id == ask.key]


def _refusal(ask: Ask) -> str:
    return NO_READER if ask.stage == "read" else NO_REVIEWER


def _default_agent(ask: Ask, writers: Sequence[str]) -> None:
    """The default agent reviews: refuse when it wrote the code or another model is asked for."""
    if "" in writers:
        raise NoAgent(_refusal(ask))
    if ask.other_model and writers:
        raise NoAgent(NO_OTHER_MODEL)


def _model(agent: TeamAgent) -> tuple[str, str, str]:
    return agent.runtime, agent.connection, agent.model


def _other_models(
    agents: Sequence[TeamAgent], writers: Sequence[str], fresh: list[TeamAgent]
) -> list[TeamAgent]:
    """The agents sharing no model with a writer; none when a writer has no definition."""
    by_name = {agent.name: agent for agent in agents}
    if any(writer not in by_name for writer in writers):
        return []
    written = {_model(by_name[writer]) for writer in writers}
    return [agent for agent in fresh if _model(agent) not in written]


def _independent(
    agents: Sequence[TeamAgent], taking: list[TeamAgent], writers: Sequence[str], ask: Ask
) -> list[TeamAgent]:
    """The agents that did not write what they judge, on another model when that is asked."""
    fresh = [agent for agent in taking if agent.name not in writers]
    if not fresh:
        raise NoAgent(_refusal(ask))
    if ask.other_model:
        fresh = _other_models(agents, writers, fresh)
    if not fresh:
        raise NoAgent(NO_OTHER_MODEL)
    return fresh


def _paused_ok(column: Sequence[TeamAgent], busy: Mapping[str, str], ask: Ask) -> list[TeamAgent]:
    """A paused agent finishes the ticket it holds and takes no other."""
    taking = [a for a in column if a.paused_at is None or busy.get(a.name) == ask.key]
    if not taking:
        role = judging(ask.stage)[0]
        raise NoAgent(f"{column[0].name} paused for {_COLUMNS.get(role, role)}")
    return taking


def _within_caps(fresh: Sequence[TeamAgent], ask: Ask) -> list[TeamAgent]:
    within = [agent for agent in fresh if at_cap(agent, ask) is None]
    if not within:
        raise NoAgent(at_cap(fresh[0], ask) or "")
    return within


def _able(within: Sequence[TeamAgent], ask: Ask) -> list[TeamAgent]:
    able = [agent for agent in within if unable(agent, ask) is None]
    if not able:
        raise NoAgent(unable(within[0], ask) or "")
    return able


def _free(able: Sequence[TeamAgent], busy: Mapping[str, str], ask: Ask) -> TeamAgent:
    for agent in able:
        if busy.get(agent.name, ask.key) == ask.key:
            return agent
    raise NoAgent(f"{able[0].name} working {busy[able[0].name]}")


def pick(agents: Sequence[TeamAgent], busy: Mapping[str, str], ask: Ask) -> TeamAgent | None:
    """The agent a run on the ticket takes; `None` is the default agent; `NoAgent` says why not.

    The first agent of the column that takes the ticket's type and labels, did not write the code
    it reviews, is within its caps, is able and holds no other ticket.
    """
    if not agents:
        return None
    worked, column = _column(agents, ask)
    writers = _writers(ask)
    if not column and worked:
        raise NoAgent(NO_MATCH)
    if not column:
        _default_agent(ask, writers)
        return None
    taking = _paused_ok(column, busy, ask)
    fresh = _independent(agents, taking, writers, ask)
    within = _within_caps(fresh, ask)
    judged = _judged(column, ask)
    return _free(_able(within, judged), busy, judged)


def passed_over(agents: Sequence[TeamAgent], taken: TeamAgent | None, ask: Ask) -> list[str]:
    """The column agents ahead of `taken` that `unable` passed over, each with why.

    A usage limit carries a `, continued by <taken>` suffix.
    """
    column = _column(agents, ask)[1]
    judged = _judged(column, ask)
    found: list[str] = []
    for agent in column:
        if taken is not None and agent.name == taken.name:
            break
        why = unable(agent, judged)
        if why is None:
            continue
        continued = taken is not None and waits_out_limit(agent, judged)
        found.append(f"{why}, continued by {taken.name}" if continued and taken else why)
    return found


@dataclass(frozen=True, slots=True)
class Team:
    """The defined agents, every run and the agents holding claims (each to its ticket's key)."""

    agents: tuple[TeamAgent, ...]
    runs: tuple[TeamRun, ...]
    busy: Mapping[str, str]
    now: float


class QueueRule:
    """The queue's rule over a team: `(key, stage, kind, labels) -> reason` ('' when it starts).

    A ticket that gets an agent makes that agent busy for the rest of one plan.
    """

    def __init__(self, team: Team) -> None:
        self._team = team
        self._busy = dict(team.busy)

    @property
    def parked(self) -> bool:
        """Whether a card parked on a usage limit is asked too: with agents defined."""
        return bool(self._team.agents)

    def __call__(self, key: str, stage: str, kind: str, labels: str) -> str:
        """Why the ticket waits, or `''` when an agent takes it."""
        team = self._team
        ask = Ask(key=key, stage=stage, kind=kind, labels=labels, runs=team.runs, now=team.now)
        try:
            agent = pick(team.agents, self._busy, ask)
        except NoAgent as refused:
            return str(refused)
        if agent is not None:
            self._busy[agent.name] = key
            return ""
        return NO_AGENT if team.agents else ""
