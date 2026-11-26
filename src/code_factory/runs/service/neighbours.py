"""The runs ports over the other modules' services.

Each class is the one place its neighbour is reached; the runs service sees the protocols of
`runs/ports.py` only. A service is looked up in the registry when it is used, so the order of
`app.MODULES` does not decide which neighbour must exist first.
"""

import hashlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from code_factory.agents.service import AgentService, StartKit
from code_factory.git.models import FetchRefusedError, TreeRedirectedError
from code_factory.git.service import GitService
from code_factory.memory_extras.models import TicketContext
from code_factory.memory_extras.service import MemoryExtrasService
from code_factory.platform.errors import ConflictError, NotFoundError, UnavailableError
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.runs.models import Run
from code_factory.runs.ports import (
    Claimed,
    Given,
    Launch,
    LaunchPlan,
    Limit,
    LogUsage,
    Settings,
    TicketFacts,
    Tree,
)
from code_factory.runs.service import RunService
from code_factory.runs.service.launching import RunLauncher
from code_factory.settings.service import SettingsService
from code_factory.team.models import ActiveRun as TeamActiveRun
from code_factory.team.models import TeamRun
from code_factory.team.service import TeamService
from code_factory.tickets.models import NewActivity
from code_factory.tickets.service import ActivityService, TicketService

PREVIEW_UNCONTAINED = (
    "a preview runs inside the sandbox, which the agents module does not build yet, "
    "so no preview starts"
)


class ConfigAdapter:
    """A repository's `config.toml` as a run reads it, and its main checkout."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def root(self, repository: str) -> Path:
        """The repository's main checkout; `NotFoundError` for one that is not tracked."""
        return await self._services.get(RepositoryService).get(repository)

    async def settings(self, repository: str) -> Settings:
        """The repository's settings with the defaults of `Settings` for what is unset."""
        config = await self._services.get(SettingsService).load(await self.root(repository))
        agents, preview = config.agents, config.preview
        found: dict[str, object] = {}
        if agents is not None:
            found = {
                "run_timeout_s": agents.run_timeout,
                "limit_wait_s": agents.limit_wait,
                "budget_usd": agents.budget_usd,
                "monthly_budget_usd": agents.monthly_budget_usd,
                "review_other_model": agents.review_other_model,
                "escalate": agents.escalate,
                "permission_reviewer": agents.permission_reviewer,
                "permission_reviewer_limit": agents.permission_reviewer_limit,
                "permission_approval": agents.permission_approval,
                "attempts": agents.attempts,
            }
        if preview is not None:
            found |= {"preview_command": preview.command, "preview_idle_s": preview.idle_seconds}
        return Settings(**{name: value for name, value in found.items() if value is not None})  # ty: ignore[invalid-argument-type]


class TicketsAdapter:
    """Tickets: the facts a start reads and the history a run appends to."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def facts(self, ticket_id: str) -> TicketFacts:
        """The ticket with the ids of its blockers that are not merged."""
        tickets = self._services.get(TicketService)
        ticket = await tickets.get(ticket_id)
        waiting = tuple([b for b in ticket.blocked_by if not (await tickets.get(b)).merged])
        return TicketFacts(
            id=ticket.id,
            number=ticket.number,
            repository=ticket.repository,
            title=ticket.title,
            kind=str(ticket.type),
            labels=tuple(ticket.labels),
            branch=ticket.branch,
            column=str(ticket.column),
            source=ticket.source,
            budget=ticket.budget,
            parallel=ticket.parallel,
            blockers=waiting,
        )

    async def record_event(
        self, ticket_id: str, kind: str, run_id: str, data: dict[str, object], at: datetime
    ) -> None:
        """Append `kind` once for the run: a repeat finds the record and adds nothing."""
        activity = self._services.get(ActivityService)
        cursor: str | None = None
        while True:
            page = await activity.list_activity(ticket_id, kinds=[kind], limit=100, cursor=cursor)
            if any(item.data.get("run") == run_id for item in page.items):
                return
            cursor = page.next_cursor
            if cursor is None:
                break
        record = NewActivity(kind=kind, data={**data, "run": run_id}, at=at)
        await activity.append(ticket_id, record, by="board")

    async def clear_branch(self, ticket_id: str) -> None:
        """Take the ticket's branch away."""
        await self._services.get(TicketService).clear_branch(ticket_id, by="board")


class TeamsAdapter:
    """The claims of the team module."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def claim_for_run(self, ticket_id: str, stage: str, settings: Settings) -> Claimed:
        """Claim the ticket and pick its agent (`ConflictError` with the sentence on refusal)."""
        claim = await self._services.get(TeamService).claim_for_run(
            ticket_id,
            stage,
            other_model=settings.review_other_model,
            escalate=settings.escalate,
        )
        name = "" if claim.agent is None else claim.agent.name
        return Claimed(agent=name, passed_over=claim.passed_over)

    async def attach_run(self, ticket_id: str, run_id: str) -> None:
        """Record the run under the claim."""
        await self._services.get(TeamService).attach_run(ticket_id, run_id)

    async def end_claim(self, ticket_id: str, run_id: str | None) -> None:
        """End the claim a run is under; a claim already gone or taken again stays."""
        try:
            await self._services.get(TeamService).end_claim(ticket_id, run_id=run_id)
        except NotFoundError, ConflictError:
            return

    async def start_refusal(self, ticket_id: str, stage: str, settings: Settings) -> str | None:
        """What claims and agents would answer a start."""
        return await self._services.get(TeamService).start_refusal(
            ticket_id,
            stage,
            other_model=settings.review_other_model,
            escalate=settings.escalate,
        )


class TreesAdapter:
    """The git module's trees."""

    def __init__(self, services: Services) -> None:
        self._services = services

    @property
    def _git(self) -> GitService:
        return self._services.get(GitService)

    async def start(self, repository: str, ticket_id: str, attempt: int) -> Tree:
        """The ticket's clone for an attempt."""
        info = await self._git.start_worktree(repository, ticket_id, attempt=attempt)
        return Tree(name=info.name, path=Path(info.path), branch=info.branch, made=info.made)

    async def head(self, tree: Tree) -> str:
        """The commit checked out in the tree."""
        return await self._git.head_of(tree.path)

    async def commits(self, repository: str, base: str, new: str) -> list[str]:
        """The commits `new` adds to `base`."""
        return [entry.commit for entry in await self._git.read_new_commits(repository, base, new)]

    async def tree_id(self, repository: str, commit: str) -> str:
        """The content hash of the fetched commit."""
        return await self._git.tree_id(repository, commit)

    async def uncommitted(self, repository: str, tree: Tree) -> bool:
        """Whether the tree holds changes that are not committed."""
        listed = await self._git.list_trees(repository)
        return any(info.name == tree.name and info.uncommitted > 0 for info in listed)

    async def fetch_back(self, repository: str, tree: Tree) -> str:
        """Bring the branch back to the main repository; why it was refused, else ''."""
        try:
            await self._git.fetch_back(repository, tree.name, tree.branch)
        except FetchRefusedError as refused:
            return str(refused)
        return ""

    async def save(self, repository: str, ticket_id: str, tree: Tree) -> None:
        """Keep the tree's unfinished work in a ref."""
        await self._git.save_work(repository, ticket_id, tree=tree.name)

    async def remove(self, repository: str, tree: Tree) -> None:
        """Remove the tree."""
        await self._git.remove_tree(repository, tree.name)

    async def redirection(self, repository: str, tree: Tree) -> str:
        """The git sentence when the tree's git folder is not the one the board made."""
        try:
            await self._git.validate_tree(repository, tree.name)
        except TreeRedirectedError as redirected:
            return str(redirected)
        return ""


class MemoryAdapter:
    """What a run is given of memory, and the record of it."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def deliver(self, run_id: str, ticket: TicketFacts, stage: str) -> str:
        """Record what the run receives; the digest of it."""
        context = TicketContext(stage=stage, labels=ticket.labels)
        recall = await self._services.get(MemoryExtrasService).deliver(
            run_id, ticket.id, ticket.repository, context
        )
        return recall.digest


class AgentsAdapter:
    """The agents module: the setup a run starts with, its model check and its log's facts."""

    def __init__(self, services: Services, launcher: RunLauncher) -> None:
        self._services = services
        self._launcher = launcher

    async def given(self, agent: str, stage: str, repository: str) -> Given:  # noqa: ARG002  # the setup does not vary by stage
        """The agent's setup (the default agent for ''), its refusal and a fingerprint of both."""
        agents = self._services.get(AgentService)
        resolved = await agents.resolve_agent(agent or None)
        definition = resolved.definition
        refusal = await agents.run_refusal(agent) if agent else None
        setup = resolved.setup
        fingerprint = hashlib.sha256(
            f"{setup.agent}|{setup.template}|{setup.model}|{setup.connection}|{refusal}".encode()
        ).hexdigest()[:16]
        return Given(
            agent=setup.agent,
            runtime=definition.runtime if definition is not None else "claude",
            model=setup.model,
            connection=setup.connection,
            fingerprint=fingerprint,
            refusal=refusal,
            max_seconds=None if definition is None else definition.max_seconds,
            max_tokens=None if definition is None else definition.max_tokens,
            input_price=None if definition is None else definition.input_price,
            output_price=None if definition is None else definition.output_price,
        )

    async def probe(self, given: Given) -> None:
        """Ask the model's server whether it answers; the check at the agents module decides."""
        if not given.agent:
            return
        refusal = await self._services.get(AgentService).run_refusal(given.agent)
        if refusal is not None and refusal != "":
            raise ConflictError(refusal)

    def launch_refusal(self, given: Given) -> str | None:
        """Why no run of the setup can launch now, from the launcher."""
        return self._launcher.launch_refusal(given)

    async def launch(self, plan: LaunchPlan) -> Launch:
        """The wrapper's command and environment, from the launcher."""
        return await self._launcher.launch(plan)

    async def log_usage(self, log: Path) -> LogUsage:
        """What the run's log reports."""
        found = await self._services.get(AgentService).usage_of_log(log)
        return LogUsage(
            cost=found.cost,
            input_tokens=found.input_tokens,
            output_tokens=found.output_tokens,
            model=found.model,
        )

    def usage_limit(self, log_text: str) -> Limit | None:
        """The usage limit the log ended on, `None` when it did not."""
        found = StartKit.usage_limit(log_text)
        return None if found is None else Limit(reset=found.reset)


class PreviewSetupAdapter:
    """A preview's tree from git; its sandbox is the agents module's, which offers none yet."""

    def __init__(self, services: Services) -> None:
        self._services = services

    async def tree_of(self, repository: str, ticket_id: str) -> Path | None:
        """The ticket's tree, `None` when it has none or its folder is not the board's."""
        for info in await self._services.get(GitService).list_trees(repository):
            if info.ticket_id == ticket_id and info.valid:
                return Path(info.path)
        return None

    async def contain(self, argv: Sequence[str], tree: Path, port: int) -> Launch:  # noqa: ARG002  # nothing builds a sandbox yet
        """`argv` inside the sandbox; the agents module provides none yet."""
        raise UnavailableError(PREVIEW_UNCONTAINED)


def epoch(moment: datetime | None) -> float | None:
    """Epoch seconds of a moment, `None` for none."""
    return None if moment is None else moment.astimezone(UTC).timestamp()


def team_run(run: Run) -> TeamRun:
    """A run as the team module reads it."""
    return TeamRun(
        id=run.id,
        ticket_id=run.ticket_key,
        repository=run.repository,
        stage=run.stage,
        agent=run.agent,
        started_at=run.started_at.timestamp(),
        ended_at=epoch(run.ended_at),
        exit_code=run.exit_code,
        tokens=run.tokens,
        cost=run.cost,
        halted=run.halted,
        limited_until=epoch(run.limited_until),
        uncommitted=run.uncommitted,
        resume_refused=run.resume_refused,
        context_at=None if run.context_at is None else int(run.context_at.timestamp()),
    )


class TeamRunSource:
    """The runs the team module reads: its `RunSource` over the run service."""

    def __init__(self, runs: Callable[[], RunService]) -> None:
        self._runs = runs

    async def runs_on_ticket(self, ticket_id: str) -> list[TeamRun]:
        """Every run of the ticket."""
        return [team_run(run) for run in await self._runs().runs_on_ticket(ticket_id)]

    async def latest_runs(self, agent_names: Sequence[str]) -> list[TeamRun]:
        """The latest run by start of each named agent."""
        return [team_run(run) for run in await self._runs().latest_runs(agent_names)]

    async def runs_since(self, moment: float) -> list[TeamRun]:
        """Every run started at or after `moment`."""
        since = datetime.fromtimestamp(moment, UTC)
        return [team_run(run) for run in await self._runs().runs_since(since)]

    async def runs_by_ids(self, ids: Sequence[str]) -> list[TeamRun]:
        """The recorded runs among `ids`."""
        return [team_run(run) for run in await self._runs().runs_by_ids(ids)]

    async def active_runs(self) -> list[TeamActiveRun]:
        """Every run with no exit and whether its process lives."""
        return [
            TeamActiveRun(run=team_run(active.run), alive=active.alive)
            for active in await self._runs().active_runs()
        ]
