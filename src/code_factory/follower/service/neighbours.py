"""The follower ports over the owning modules' services, resolved from the registry per call."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import override

from code_factory.board.service import CardQueue
from code_factory.checks.service import CheckService
from code_factory.evals.service import JudgeService
from code_factory.follower.models import ActiveRunFact, Card
from code_factory.follower.rules import due_for_fix, due_for_review, failure_streak
from code_factory.follower.rules.filing import main_failure_fields, revert_fields
from code_factory.follower.rules.queue import Rule, reader_due, ready, roles_due
from code_factory.follower.service import QueueService
from code_factory.follower.service.repairs import repairs_for
from code_factory.metrics.service import MetricsService
from code_factory.platform.errors import ConflictError
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.runs.models import Repair, RunView, StartOptions
from code_factory.runs.service import RunService
from code_factory.settings.models import ConfigUnjudgedError, reviews
from code_factory.settings.service import SettingsService
from code_factory.stages.models import StageAssessment
from code_factory.stages.service import StageService
from code_factory.talk.models import QuestionFilter
from code_factory.talk.service import TalkService
from code_factory.team.service import TeamService
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import NewTicket, Ticket
from code_factory.tickets.service import DocumentService, TicketService

DEFAULT_SLOTS = 1
PAGE = 100


def _budget(text: str) -> float | None:
    try:
        return float(text) if text.strip() else None
    except ValueError:
        return None


def _history(views: list[RunView]) -> tuple[int, datetime | None, datetime | None]:
    """Of a ticket's runs, newest first: the failures in a row, the last end and its limit."""
    ended = next((v for v in views if v.state != "running"), None)
    if ended is None:
        return 0, None, None
    return failure_streak([v.state for v in views]), ended.ended_at, ended.limited_until


class _Neighbour:
    def __init__(self, services: Services) -> None:
        self._services = services

    async def _config(self, repository: str) -> object | None:
        root = await self._services.get(RepositoryService).get(repository)
        try:
            return await self._services.get(SettingsService).load(Path(root))
        except ConfigUnjudgedError:
            return None


class BoardAdapter(_Neighbour):
    """Cards, runs, caps and the team's rule."""

    async def _unanswered(self) -> dict[str, int]:
        talk = self._services.get(TalkService)
        counts: dict[str, int] = {}
        cursor: str | None = None
        while True:
            page = await talk.list(QuestionFilter(status="open"), limit=PAGE, cursor=cursor)
            for question in page.items:
                counts[question.ticket_id] = counts.get(question.ticket_id, 0) + 1
            cursor = page.next_cursor
            if cursor is None:
                return counts

    async def _spent(self, ticket: Ticket) -> float:
        if _budget(ticket.budget) is None:
            return 0.0
        runs = await self._services.get(RunService).runs_on_ticket(ticket.id)
        return sum(run.cost or 0.0 for run in runs)

    async def _review_on(self, repository: str, known: dict[str, bool]) -> bool:
        if repository not in known:
            agents = getattr(await self._config(repository), "agents", None)
            known[repository] = reviews(agents)
        return known[repository]

    async def _roles_due(
        self, ticket: Ticket, views: list[RunView], roles: dict[str, list[str]]
    ) -> list[str]:
        """The review roles the repository sets that have not run since the latest build."""
        if ticket.repository not in roles:
            agents = getattr(await self._config(ticket.repository), "agents", None)
            roles[ticket.repository] = list(getattr(agents, "review_roles", None) or [])
        ended = [
            (v.stage, v.started_at, v.state == "finished") for v in views if v.state != "running"
        ]
        return roles_due(roles[ticket.repository], ended)

    async def _reader_due(
        self, ticket: Ticket, views: list[RunView], readers: dict[str, tuple[bool, bool]]
    ) -> str:
        """The second reader the repository asks for that the Build ticket still wants."""
        if ticket.repository not in readers:
            agents = getattr(await self._config(ticket.repository), "agents", None)
            readers[ticket.repository] = (
                getattr(agents, "spec_reader", None) is True,
                getattr(agents, "plan_critic", None) is True,
            )
        spec_reader, plan_critic = readers[ticket.repository]
        ended = [
            (v.stage, v.started_at, v.state == "finished") for v in views if v.state != "running"
        ]
        return reader_due(ended, spec_reader=spec_reader, plan_critic=plan_critic)

    async def _due(
        self,
        ticket: Ticket,
        facts: StageAssessment | None,
        views: list[RunView],
        known: dict[str, bool],
    ) -> tuple[bool, bool]:
        """Whether the ticket wants a review run, and whether it wants a fix run."""
        if facts is None:
            return False, False
        ended = [v for v in views if v.state != "running"]
        last_stage = ended[0].stage if ended else None
        review = due_for_review(
            facts.stage,
            review_on=await self._review_on(ticket.repository, known),
            last_stage=last_stage,
        )
        returned_at = None
        if facts.declared == "build":
            verdicts = await self._services.get(StageService).review_verdicts(ticket.id)
            latest = next((v for v in reversed(verdicts) if v.outcome != "skipped"), None)
            returned_at = latest.at if latest is not None and latest.outcome == "returned" else None
        runs = [(v.started_at, bool(v.commits)) for v in ended]
        return review, due_for_fix(facts.stage, returned_at, runs)

    async def _build_extras(
        self,
        ticket: Ticket,
        views: list[RunView],
        readers: dict[str, tuple[bool, bool]],
        *,
        stage: str,
        fix_due: bool,
    ) -> tuple[list[str], str]:
        """The document gaps of a ticket in build, and the reader role it is due, if any."""
        if stage != "build":
            return [], ""
        gaps = await self._services.get(DocumentService).build_gaps(ticket.id)
        if fix_due or gaps:
            return gaps, ""
        return gaps, await self._reader_due(ticket, views, readers)

    async def cards(self) -> list[Card]:
        """Every live ticket as a queue card."""
        tickets = await self._services.get(TicketService).list()
        relevant = dict.fromkeys(i for t in tickets for i in (t.id, *t.blocked_by))
        assessed = await self._services.get(StageService).assess_many(list(relevant))
        landed = {i for i, facts in assessed.items() if facts.derived in {"merged", "released"}}
        unanswered = await self._unanswered()
        runs = self._services.get(RunService)
        running = {a.run.ticket_key for a in await runs.active_runs()}
        history = await runs.card_runs([t.id for t in tickets])
        repairs = await repairs_for(self._services, assessed, running)
        known: dict[str, bool] = {}
        roles: dict[str, list[str]] = {}
        readers: dict[str, tuple[bool, bool]] = {}
        cards = []
        for ticket in tickets:
            facts = assessed.get(ticket.id)
            views = history.get(ticket.id, [])
            failures, last_end, limited_until = _history(views)
            repair = repairs.get(ticket.id)
            if repair is None:
                stage = facts.stage if facts else str(ticket.column)
                review_due, fix_due = await self._due(ticket, facts, views, known)
            else:
                stage, review_due, fix_due = "build", False, True
            due_roles = await self._roles_due(ticket, views, roles) if review_due else []
            gaps, reader = await self._build_extras(
                ticket, views, readers, stage=stage, fix_due=fix_due
            )
            card = Card(
                id=ticket.id,
                repository=ticket.repository,
                stage=stage,
                priority=str(ticket.priority),
                rank=ticket.rank,
                archived=ticket.archived,
                blocked=ticket.blocked,
                work_done=bool(facts and facts.work_done),
                runs=1 if ticket.id in running else 0,
                unanswered=unanswered.get(ticket.id, 0),
                open_blockers=tuple(
                    b for b in ticket.blocked_by if b in assessed and b not in landed
                ),
                budget=_budget(ticket.budget),
                spent=await self._spent(ticket),
                kind=str(ticket.type),
                labels=",".join(ticket.labels),
                failures=failures,
                last_end=last_end,
                limited_until=limited_until,
                review_due=review_due,
                fix_due=fix_due,
                repair=repair,
                build_gaps=tuple(gaps),
                run_stage=due_roles[0] if due_roles else reader,
            )
            if repair is not None and ready(card):
                hold = await runs.repair_refusal(ticket.id, repair)
                card = card.model_copy(update={"repair_hold": hold})
            cards.append(card)
        return cards

    async def active(self) -> list[ActiveRunFact]:
        """Runs with no exit."""
        return [
            ActiveRunFact(
                repository=a.run.repository,
                ticket_id=a.run.ticket_key,
                stage=a.run.stage,
                active=a.alive,
            )
            for a in await self._services.get(RunService).active_runs()
        ]

    async def slots(self) -> dict[str, int]:
        """Each tracked repository's `[agents] slots`, 1 when unset."""
        found: dict[str, int] = {}
        for record in await self._services.get(RepositoryService).list():
            config = await self._config(record.name)
            agents = getattr(config, "agents", None)
            set_slots = getattr(agents, "slots", None)
            found[record.name] = int(set_slots) if set_slots is not None else DEFAULT_SLOTS
        return found

    async def overall(self) -> int | None:
        """The board's cap over all repositories."""
        return (await self._services.get(SettingsService).board_settings()).agent_slots

    async def limits(self) -> dict[str, int]:
        """Each limited column's limit."""
        return await self._services.get(TicketWriteService).column_limits()

    async def rule(self, ids: list[str]) -> Rule:
        """The team's say: which agent takes each card."""
        team_rule = await self._services.get(TeamService).queue_rule(ids)
        return lambda card: team_rule(card.id, card.stage, card.kind, card.labels)


class WorkAdapter(_Neighbour):
    """The loops a pass drives and the run start."""

    async def collect(self) -> int:
        """End finished runs."""
        return len(await self._services.get(RunService).collect())

    async def keep(self) -> int:
        """Keep the team's leases."""
        return await self._services.get(TeamService).keep()

    async def observe(self) -> int:
        """Observe the stages."""
        return (await self._services.get(StageService).observe()).observed

    async def start(self, ticket_id: str, stage: str, repair: Repair | None = None) -> None:
        """Start the stage, supplying the check evidence when it is a repair."""
        if repair is not None:
            repair = await self._current_repair(ticket_id, repair)
        options = StartOptions(looping=stage in {"spec", "build"}, repair=repair)
        await self._services.get(RunService).start(ticket_id, stage=stage, options=options)

    async def _current_repair(self, ticket_id: str, planned: Repair) -> Repair:
        """Recheck evidence that could have changed while the ticket waited for its slot."""
        stages = self._services.get(StageService)
        facts = await stages.assess(ticket_id)
        current = (await repairs_for(self._services, {ticket_id: facts}, set())).get(ticket_id)
        if current is None or current.head != planned.head or current.reason != planned.reason:
            msg = "the repair evidence changed before the Build run could start"
            raise ConflictError(msg)
        if (
            current.reason == "ci"
            and (task := await stages.checks_task(ticket_id, current.head)) is not None
        ):
            return current.model_copy(update={"task": task})
        return current


class FilingAdapter(_Neighbour):
    """Recurring and scorer tickets."""

    async def repositories(self) -> list[str]:
        """Every tracked repository."""
        return [r.name for r in await self._services.get(RepositoryService).list()]

    async def recurring(self, repository: str) -> list[Mapping[str, object]]:
        """The `[[recurring]]` entries."""
        config = await self._config(repository)
        entries = getattr(config, "recurring", None) or []
        return [entry.model_dump() for entry in entries]

    async def sources(self, repository: str) -> set[str]:
        """The sources of the repository's tickets, archived ones too."""
        tickets = await self._services.get(TicketService).list()
        return {t.source for t in tickets if t.repository == repository and t.source}

    async def file(self, repository: str, fields: Mapping[str, object]) -> str:
        """File a ticket from fields."""
        new = NewTicket.model_validate({"repository": repository, **fields})
        return (await self._services.get(TicketService).create(new, by="board")).id

    async def failures(self, repository: str) -> list[Mapping[str, object]]:
        """The bug tickets a failing default branch and the reverted merges file, as fields."""
        failing = await self._services.get(CheckService).failing_default_branches()
        fields: list[Mapping[str, object]] = [
            main_failure_fields(
                repository=f.repository,
                commit=f.commit,
                step=f.step,
                broken_by=f.broken_by,
                passed=f.passed,
                ticket=f.ticket,
            )
            for f in failing
            if f.repository == repository
        ]
        flow = await self._services.get(MetricsService).flow()
        fields += [
            revert_fields(m.title, m.branch, m.ticket)
            for m in flow.merged
            if m.reverted and m.repository == repository
        ]
        return fields

    async def scorer_firings(self, repository: str) -> list[Mapping[str, object]]:
        """The scorer tickets due, as ticket fields."""
        firings = await self._services.get(JudgeService).scorer_firings(repository)
        return [
            {
                "title": f.title,
                "description": f.body,
                "source": f.source,
                "type": f.kind,
                "labels": [f.label],
            }
            for f in firings
        ]


class QueueAdapter(_Neighbour, CardQueue):
    """The board's `CardQueue`: the plan of the follower's last pass and the team's claims."""

    def __init__(self, services: Services, queue: QueueService) -> None:
        super().__init__(services)
        self._queue = queue

    @override
    async def queue_plan(self) -> dict[str, str]:
        return await self._queue.plan()

    @override
    async def holders(self, ticket_ids: Sequence[str]) -> dict[str, str]:
        return await self._services.get(TeamService).holders(list(ticket_ids))
