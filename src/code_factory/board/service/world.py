"""What every card of one read shares: the tickets, where each stands, repositories, sessions."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from pathlib import Path

from code_factory.board.models import Placement, RepositoryFacts, SessionFacts
from code_factory.board.rules.links import Relations
from code_factory.board.rules.marks import entered_column
from code_factory.board.rules.order import rank_key
from code_factory.board.service.sources import BoardSources
from code_factory.sessions.models import AtWork
from code_factory.settings.models import ConfigUnjudgedError
from code_factory.settings.service import CONFIG_FILE
from code_factory.stages.models import StageAssessment
from code_factory.tickets.models import ActivityMarks, Ticket, TicketFilter


@dataclass(frozen=True)
class World:
    """One read's shared facts. Separate modules answer separately: a few milliseconds of skew."""

    now: datetime
    tickets: list[Ticket]
    placements: dict[str, StageAssessment]
    repositories: dict[str, RepositoryFacts]
    sessions: list[SessionFacts]
    at_work: list[AtWork]
    queue_plan: dict[str, str]
    marks: dict[str, ActivityMarks]
    problems: list[dict[str, str]]

    def stage_of(self, ticket: Ticket) -> str:
        """The column the ticket stands in; `released` once a release named it."""
        placed = self.placements.get(ticket.id)
        return placed.stage if placed else ticket.column.value

    def placement(self, ticket: Ticket) -> Placement:
        """Where the ticket stands and what holds it there."""
        placed = self.placements.get(ticket.id)
        if placed is None:
            return Placement(stage=ticket.column.value, evidence_stage=ticket.column.value)
        return Placement(
            stage=placed.stage,
            evidence_stage=placed.derived,
            declared=placed.declared,
            hold=placed.hold,
        )

    def entered(self, ticket: Ticket) -> datetime:
        """When the ticket entered the column it stands in."""
        return entered_column(ticket, self.marks.get(ticket.id))

    def relations(self) -> Relations:
        """The links among every ticket, whatever repository it is in."""
        return Relations(self.tickets, {t.id: self.stage_of(t) for t in self.tickets})

    def on_board(self) -> list[Ticket]:
        """The tickets with a card: not archived and not released."""
        return [t for t in self.tickets if not t.archived and self.stage_of(t) != "released"]


def _dollars(amount: float | None) -> float | None:
    return float(amount) if amount is not None and isfinite(amount) else None


async def _repository_facts(
    sources: BoardSources,
    repository: str | None = None,
) -> tuple[dict[str, RepositoryFacts], list[dict[str, str]]]:
    """Each tracked repository's facts; one whose settings were not judged in time is a problem."""
    found: dict[str, RepositoryFacts] = {}
    problems: list[dict[str, str]] = []
    for record in await sources.repositories.list():
        if repository is not None and record.name != repository:
            continue
        try:
            config = await sources.settings.load(Path(record.path))
            agents, checks = config.agents, config.checks
        except ConfigUnjudgedError as unjudged:
            agents = checks = None
            problems.append(
                {
                    "repository": record.name,
                    "file": CONFIG_FILE,
                    "path": str(Path(record.path) / CONFIG_FILE),
                    "reason": str(unjudged),
                }
            )
        found[record.name] = RepositoryFacts(
            name=record.name,
            path=record.path,
            budget_usd=_dollars(agents.budget_usd if agents else None),
            monthly_budget_usd=_dollars(agents.monthly_budget_usd if agents else None),
            checks_configured=bool(checks and checks.command),
        )
    return found, problems


async def read_tickets(sources: BoardSources) -> list[Ticket]:
    """Every ticket, archived and released too."""
    return await sources.tickets.list(TicketFilter(archived=None))


async def read_placed(sources: BoardSources) -> tuple[list[Ticket], dict[str, StageAssessment]]:
    """Every ticket, archived and released too, and where each stands."""
    tickets = await read_tickets(sources)
    return tickets, await sources.stages.assess_tickets(tickets)


async def _page_tickets(sources: BoardSources, ticket: Ticket) -> list[Ticket]:
    same = await sources.tickets.list(TicketFilter(repository=ticket.repository, archived=None))
    linked = await sources.tickets.linking_to(ticket.id)
    if ticket.parent:
        linked.append(ticket.parent)
    linked.extend(ticket.blocked_by)
    local = {ticket.id, *(t.id for t in same)}
    others = list(dict.fromkeys(i for i in linked if i not in local))
    found = [ticket, *(t for t in same if t.id != ticket.id)]
    found.extend(await sources.tickets.list(TicketFilter(ids=others, archived=None)))
    return sorted(found, key=lambda t: rank_key(t.rank, t.id))


async def read_world(sources: BoardSources, now: datetime, ticket: Ticket | None = None) -> World:
    """Read the board's facts or the subset a ticket page needs."""
    if ticket is None:
        tickets, placements = await read_placed(sources)
        marks = [t.id for t in tickets]
    else:
        tickets = await _page_tickets(sources, ticket)
        placements = await sources.stages.assess_tickets(tickets)
        marks = [ticket.id]
    seconds = now.timestamp()
    views = await sources.sessions.board_views(seconds)
    repositories, problems = await _repository_facts(sources, ticket.repository if ticket else None)
    return World(
        now=now,
        tickets=tickets,
        placements=placements,
        repositories=repositories,
        sessions=[
            SessionFacts(session_id=v.session_id, cwd=v.cwd, branch=v.branch, state=v.state.value)
            for v in views
        ],
        at_work=await sources.sessions.subagents_at_work(seconds, fresh_only=True),
        queue_plan=await sources.queue.queue_plan(),
        marks=await sources.activity.latest_marks(marks),
        problems=problems,
    )
