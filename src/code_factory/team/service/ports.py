"""What the team reads from the other modules, as ports.

The team imports no other domain module. Each providing module registers an adapter under the
port's class in its own `provide` (`services.add(AgentSource, ...)`), importing this file; the
service resolves them lazily through `TeamPorts`, so no import cycle can form.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from code_factory.team.models import (
    ActiveRun,
    AtWork,
    LandJob,
    OwnerItem,
    RepositoryRef,
    RunningGate,
    TeamAgent,
    TeamRun,
    TicketAsk,
    TicketFacts,
)


class AgentSource(Protocol):
    """The agents module: the defined agents and their failed model checks."""

    async def team_agents(self) -> list[TeamAgent]:
        """Every defined agent in roster order; `refusal` is the failed model check sentence."""
        ...


class RunSource(Protocol):
    """The runs module."""

    async def runs_on_ticket(self, ticket_id: str) -> list[TeamRun]:
        """Every run of the ticket; tokens are live for the active ones."""
        ...

    async def latest_runs(self, agent_names: Sequence[str]) -> list[TeamRun]:
        """The latest run by start of each named agent."""
        ...

    async def runs_since(self, moment: float) -> list[TeamRun]:
        """Every run started at or after `moment` (epoch seconds)."""
        ...

    async def runs_by_ids(self, ids: Sequence[str]) -> list[TeamRun]:
        """The recorded runs among `ids`; an id with no record is left out."""
        ...

    async def active_runs(self) -> list[ActiveRun]:
        """Every run with no exit and whether its process lives."""
        ...


class TicketSource(Protocol):
    """The tickets module."""

    async def team_facts(self, since: float) -> list[TicketFacts]:
        """Non-archived tickets, merged ones only at or after `since`.

        Each carries its activities of kinds `created, checks, pull_request, branch_conflict,
        ship_started, ship_pushed, ship_failed, branch_pushed` plus the newest 5 of any kind, each
        with its `words`, oldest first.
        """
        ...

    async def repositories(self) -> list[RepositoryRef]:
        """The tracked repositories."""
        ...

    async def ticket_ask(self, ticket_id: str) -> TicketAsk:
        """The ticket's type, labels and repository; `NotFoundError` for an unknown ticket."""
        ...


class GateSource(Protocol):
    """The checks module."""

    async def running_gates(self) -> list[RunningGate]:
        """The gates running or queued, with the `gate: ` lines of their logs."""
        ...


class OwnerSource(Protocol):
    """The inbox module."""

    async def owner_items(self) -> list[OwnerItem]:
        """What waits on the owner: kind `questions`, `screens` or `stopped`."""
        ...


class SessionSource(Protocol):
    """The sessions module."""

    async def subagents_at_work(self) -> list[AtWork]:
        """Running subagents that work on a ticket."""
        ...


class JobSource(Protocol):
    """The module that runs land jobs."""

    async def running_land_jobs(self) -> list[LandJob]:
        """Land jobs recorded running."""
        ...


@dataclass(frozen=True, slots=True)
class TeamPorts:
    """Every port, resolved together at the time of a call."""

    agents: AgentSource
    runs: RunSource
    tickets: TicketSource
    gates: GateSource
    owner: OwnerSource
    sessions: SessionSource
    jobs: JobSource
