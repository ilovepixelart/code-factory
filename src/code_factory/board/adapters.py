"""The team page's ports over the board's reads, and the board's queue over the team's claims.

Tickets, repositories and talk answer the team; land jobs are empty. The agents, runs, checks and
sessions modules register the team's other ports; a class is registered once
(`tests/unit/test_composition.py`).
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import override

from code_factory.board.models import ActivityRecord, CheckRecord, PullFacts
from code_factory.board.rules.parts import latest_check
from code_factory.repositories.service import RepositoryService
from code_factory.talk.models import QuestionFilter
from code_factory.talk.service import TalkService
from code_factory.team.models import (
    LandJob,
    OwnerItem,
    RepositoryRef,
    TeamActivity,
    TicketAsk,
    TicketFacts,
    TicketRef,
)
from code_factory.team.service import JobSource
from code_factory.tickets.models import ActivityEntry, Column, Ticket
from code_factory.tickets.service import ActivityService, TicketService, describe

# What TicketSource promises: every record of these kinds, and the newest few of any kind.
_TEAM_KINDS = frozenset(
    {
        "created",
        "checks",
        "pull_request",
        "branch_conflict",
        "ship_started",
        "ship_pushed",
        "ship_failed",
        "branch_pushed",
    }
)
_NEWEST = 5
DeliveryEvents = Callable[[Sequence[str]], Awaitable[dict[str, list[ActivityRecord]]]]
LedgerMerges = Callable[[Sequence[str]], Awaitable[dict[str, float]]]
DeliveryPulls = Callable[[Sequence[str]], Awaitable[dict[str, PullFacts]]]
CheckRecords = Callable[[dict[str, str]], Awaitable[dict[str, list[CheckRecord]]]]


@dataclass(frozen=True, slots=True)
class TeamReads:
    """The other modules' bulk reads the team's tickets are built from."""

    events: DeliveryEvents
    merges: LedgerMerges
    pulls: DeliveryPulls
    checks: CheckRecords


def _verdict(records: list[CheckRecord], pull: PullFacts | None) -> bool | None:
    """The checks verdict on the pull's head, by the rule the ticket page's card reads."""
    check = latest_check(records, pull.head if pull else "", pull)
    return None if check is None else bool(check["passed"])


def _history(
    entries: Sequence[ActivityEntry], events: Sequence[ActivityRecord]
) -> list[TeamActivity]:
    """The ticket's records and its delivery records the team reads, oldest first."""
    records = sorted(
        [
            *(
                TeamActivity(at=e.at.timestamp(), kind=e.kind, data=e.data, words=e.sentence)
                for e in entries
            ),
            *(
                TeamActivity(at=e.at, kind=e.kind, data=e.data, words=describe(e.kind, e.data))
                for e in events
            ),
        ],
        key=lambda record: record.at,
    )
    newest = len(records) - _NEWEST
    return [r for i, r in enumerate(records) if i >= newest or r.kind in _TEAM_KINDS]


def _merged_at(events: Sequence[ActivityRecord], landed: float | None) -> float | None:
    """When the ticket merged: its ledger merge (what Flow counts) or merge record, earliest."""
    moments = [e.at for e in events if e.kind == "merged_pull_request"]
    if landed is not None:
        moments.append(landed)
    return min(moments, default=None)


class TeamTickets:
    """The team's view of tickets (`TicketSource`)."""

    def __init__(
        self,
        tickets: TicketService,
        repositories: RepositoryService,
        activity: ActivityService,
        reads: TeamReads,
    ) -> None:
        self._tickets = tickets
        self._repositories = repositories
        self._activity = activity
        self._reads = reads

    @staticmethod
    def _entered(ticket: Ticket, entries: Sequence[ActivityEntry]) -> float:
        """When the ticket entered its column: its last move there, else when it was last edited."""
        for record in reversed(entries):
            if (
                record.kind == "stage"
                and str(record.data.get("to", "")).lower() == ticket.column.value
            ):
                return record.at.timestamp()
        return ticket.updated_at.timestamp()

    async def team_facts(self, since: float) -> list[TicketFacts]:
        """Open tickets, and merged ones whose merge was recorded at or after `since`."""
        tickets = await self._tickets.list()
        ids = [t.id for t in tickets]
        events = await self._reads.events(ids)
        landed = await self._reads.merges([t.id for t in tickets if t.column is Column.MERGED])
        visible: list[tuple[Ticket, float | None]] = []
        for ticket in tickets:
            own = events.get(ticket.id, [])
            merged = (
                _merged_at(own, landed.get(ticket.id)) if ticket.column is Column.MERGED else None
            )
            if ticket.column is Column.MERGED and (merged is None or merged < since):
                continue
            visible.append((ticket, merged))

        shown = [ticket.id for ticket, _ in visible]
        pulls = await self._reads.pulls(shown)
        checks = await self._reads.checks(
            {ticket: pulls[ticket].head if ticket in pulls else "" for ticket in shown}
        )
        histories = await self._activity.selected_entries(
            shown, kinds=_TEAM_KINDS | {"stage"}, newest=_NEWEST
        )
        found = []
        for ticket, merged in visible:
            entries = histories.get(ticket.id, [])
            waiting = ticket.column in {Column.REVIEW, Column.MERGED}
            moment = self._entered(ticket, entries) if waiting else ticket.updated_at.timestamp()
            request = ticket.pull_request
            pull = (request.url, request.state.value) if request else None
            found.append(
                TicketFacts(
                    reference=TicketRef(
                        repository=ticket.repository, id=ticket.id, title=ticket.title
                    ),
                    kind=ticket.type,
                    column=ticket.column.value,
                    column_since=moment,
                    merged=merged,
                    pull=pull,
                    activities=tuple(_history(entries, events.get(ticket.id, []))),
                    check=_verdict(checks.get(ticket.id, []), pulls.get(ticket.id)),
                )
            )
        return found

    async def repositories(self) -> list[RepositoryRef]:
        """The tracked repositories."""
        return [RepositoryRef(name=r.name, path=r.path) for r in await self._repositories.list()]

    async def ticket_ask(self, ticket_id: str) -> TicketAsk:
        """The ticket's type, labels and repository."""
        ticket = await self._tickets.get(ticket_id)
        return TicketAsk(
            kind=ticket.type, labels=", ".join(ticket.labels), repository=ticket.repository
        )


class TeamOwner:
    """What waits on the owner (`OwnerSource`): the tickets with open questions."""

    def __init__(self, tickets: TicketService, talk: TalkService) -> None:
        self._tickets = tickets
        self._talk = talk

    async def owner_items(self) -> list[OwnerItem]:
        """One item per ticket with open questions, since its oldest."""
        oldest: dict[str, float] = {}
        counts: dict[str, int] = {}
        cursor = None
        while True:
            page = await self._talk.list(QuestionFilter(status="open"), limit=100, cursor=cursor)
            for question in page.items:
                oldest[question.ticket_id] = min(
                    oldest.get(question.ticket_id, float("inf")), question.created_at.timestamp()
                )
                counts[question.ticket_id] = counts.get(question.ticket_id, 0) + 1
            cursor = page.next_cursor
            if cursor is None:
                break
        items = []
        for ticket_id, since in oldest.items():
            ticket = await self._tickets.get(ticket_id)
            reference = TicketRef(repository=ticket.repository, id=ticket.id, title=ticket.title)
            items.append(
                OwnerItem(ticket=reference, kind="questions", since=since, count=counts[ticket_id])
            )
        return items


class NoJobs(JobSource):
    """`JobSource` before land jobs exist: none running."""

    @override
    async def running_land_jobs(self) -> list[LandJob]:
        """None."""
        return []
