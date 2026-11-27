"""Starting a run: guards, the claim, the checks, the tree, the row, the process."""

import logging
import secrets
from copy import copy
from dataclasses import dataclass, field
from pathlib import Path

from code_factory.platform.errors import (
    BadRequestError,
    CodeFactoryError,
    ConflictError,
    UnavailableError,
)
from code_factory.runs.adapters.processes import Spawned, Target
from code_factory.runs.models import (
    PERMISSION_MODES,
    Run,
    Started,
    StartOptions,
)
from code_factory.runs.ports import Given, LaunchPlan, Settings, TicketFacts, Tree
from code_factory.runs.repository import HaltRepository, RunEnd, RunRepository
from code_factory.runs.rules import budget as budget_rules
from code_factory.runs.rules.budget import Spent
from code_factory.runs.service.reading import Reading

logger = logging.getLogger(__name__)

HALTED = "agents are stopped; resume them on the board or with code-factory resume"
ALREADY_RUNNING = "an agent is already running on this ticket"
NO_SPLIT_PROMPT = "a split run starts only from code-factory split, which gives its prompt"
SETTINGS_CHANGED = (
    "the run's settings changed while the start waited on its model's server; start it again"
)
STAGES_WITH_NO_AGENT = ("merged",)
TOKEN_GRACE_S = 300
UNKNOWN = -1


def blocked_refusal(waiting: tuple[str, ...]) -> str | None:
    """Why a ticket waiting on unfinished blockers cannot start an agent."""
    if not waiting:
        return None
    verb = "which is" if len(waiting) == 1 else "which are"
    return f"blocked by {', '.join(waiting)}, {verb} not done"


@dataclass
class _Start:
    """One start's inputs and what its steps made, so a failure can undo each."""

    facts: TicketFacts
    stage: str
    options: StartOptions
    settings: Settings = field(default_factory=Settings)
    given: Given | None = None
    tree: Tree | None = None
    remaining: float | None = None
    run: Run | None = None
    spawned: Spawned | None = None
    attached: bool = False
    count: int = 1

    def made(self) -> tuple[Run, Tree, Given]:
        """The run, its tree and its setup, once `_begin` made them."""
        assert self.run is not None  # noqa: S101  # `_begin` returned without raising
        assert self.tree is not None  # noqa: S101
        assert self.given is not None  # noqa: S101
        return self.run, self.tree, self.given


class Starting(Reading):
    """The start of a run."""

    async def _halted(self) -> bool:
        async with self._uow() as session:
            return await HaltRepository(session).halted() is not None

    def _check_ask(self, facts: TicketFacts, stage: str, options: StartOptions) -> None:
        if options.permissions not in PERMISSION_MODES:
            msg = "unknown permission mode"
            raise BadRequestError(msg)
        if stage == "split" and options.prompt is None:
            raise ConflictError(NO_SPLIT_PROMPT)
        if stage in STAGES_WITH_NO_AGENT:
            msg = f"nothing for an agent to do at {stage}"
            raise ConflictError(msg)
        if (why := blocked_refusal(facts.blockers)) is not None:
            raise ConflictError(why)

    async def _settled_given(self, claimed_agent: str, stage: str) -> Given:
        agents = self._ports.agents
        given = await agents.given(claimed_agent, stage)
        if given.refusal is not None:
            raise ConflictError(given.refusal)
        await agents.probe(given)  # no lock and no transaction is held while the server answers
        again = await agents.given(claimed_agent, stage)
        if again.fingerprint != given.fingerprint:
            raise ConflictError(SETTINGS_CHANGED)
        return given

    async def start_refusal(self, ticket_id: str, stage: str | None = None) -> str | None:
        """Why a start would be refused, `None` when it would not; read only."""
        facts = await self._ports.tickets.facts(ticket_id)
        if await self._halted():
            return HALTED
        async with self._uow() as session:
            held = await RunRepository(session).for_ticket(facts.number)
        if any(run.exit_code is None for run in held):
            return ALREADY_RUNNING
        settings = await self._ports.config.settings(facts.repository)
        return await self._ports.teams.start_refusal(ticket_id, stage or facts.column, settings)

    async def start(
        self,
        ticket_id: str,
        *,
        stage: str | None = None,
        agent: str | None = None,  # noqa: ARG002  # the claim picks the agent
        options: StartOptions | None = None,
    ) -> Started:
        """Start a run of the ticket; the refusal is a sentence (`ConflictError`).

        A claim is taken first and given back on any failure after it. A failure after the row
        exists ends the row (-1) with the reason, revokes its token and leaves no process.
        """
        facts = await self._ports.tickets.facts(ticket_id)
        begin = _Start(facts, stage or facts.column, options or StartOptions())
        if await self._halted():
            raise ConflictError(HALTED)
        self._check_ask(facts, begin.stage, begin.options)
        begin.settings = await self._ports.config.settings(facts.repository)
        claimed = await self._ports.teams.claim_for_run(ticket_id, begin.stage, begin.settings)
        begin.count = budget_rules.attempt_count(facts.parallel, begin.settings.attempts)
        return Started(runs=await self._start_attempts(begin, claimed.agent))

    async def _start_attempts(self, first: _Start, agent: str) -> list[Run]:
        """One run, or a build's parallel attempts one after the other under the one claim.

        A failure ends that run and its process; the claim goes back only when no run holds it.
        """
        options = first.options
        parallel = first.stage == "build" and options.attempt == 0 and first.count > 1
        attempts = range(1, first.count + 1) if parallel else [options.attempt]
        runs: list[Run] = []
        for attempt in attempts:
            begin = copy(first)
            begin.options = options.model_copy(update={"attempt": attempt})
            try:
                await self._begin(begin, agent)
                runs.append(await self._launch(begin))
            except BaseException as failure:
                await self._abandon(begin, failure, release_claim=not runs)
                raise
            first.given = begin.given  # one probe for every attempt
        return runs

    async def _begin(self, begin: _Start, agent: str) -> None:
        facts, options = begin.facts, begin.options
        given = begin.given = begin.given or await self._settled_given(agent, begin.stage)
        remaining = budget_rules.remaining_budget(
            await self.scopes(facts, begin.settings), options.attempt, begin.count
        )
        if isinstance(remaining, Spent):
            raise ConflictError(remaining.note)
        begin.remaining = remaining
        if (refusal := self._ports.agents.launch_refusal(given)) is not None:
            raise UnavailableError(refusal)
        tree = begin.tree = await self._ports.trees.start(
            facts.repository, facts.id, options.attempt
        )
        head = await self._ports.trees.head(tree)
        run_id = secrets.token_hex(6)
        now = self._clock()
        run = Run(
            id=run_id,
            ticket_id=facts.number,
            ticket_key=facts.id,
            repository=facts.repository,
            branch=tree.branch,
            worktree=str(tree.path),
            log=str(self.log_path(run_id)),
            stage=begin.stage,
            started_at=now,
            awake_started_at=now,
            looping=options.looping,
            permissions=options.permissions,
            iteration=options.iteration,
            attempt=options.attempt,
            agent=given.agent,
            model=given.model,
            connection=given.connection,
            head=head,
        )
        async with self._uow() as session:
            await RunRepository(session).insert(run)
        begin.run = run

    async def _launch(self, begin: _Start) -> Run:
        run, tree, given = begin.made()
        facts = begin.facts
        digest = await self._ports.memory.deliver(run.id, facts, run.stage)
        limit = given.max_seconds or begin.settings.run_timeout_s
        token = await self._ports.tokens.issue(
            run.id, facts.id, run.stage, run.repository, limit + TOKEN_GRACE_S
        )
        plan = LaunchPlan(
            run_id=run.id,
            stage=run.stage,
            ticket=facts,
            tree=tree,
            given=given,
            permissions=run.permissions,
            remaining=begin.remaining,
            exit_file=self.exit_path(run.id),
            log=Path(run.log),
            prompt=begin.options.prompt,
            nudge=begin.options.nudge,
            looping=run.looping,
            iteration=run.iteration,
            timeout_s=limit,
            lifetime_s=limit + TOKEN_GRACE_S,
            token=token,
        )
        launch = await self._ports.agents.launch(plan)
        async with self._start_slots:
            begin.spawned = await self._registry.spawn(
                launch.argv, env=launch.env, cwd=tree.path, log=Path(run.log)
            )
        spawned = begin.spawned
        async with self._uow() as session:
            repo = RunRepository(session)
            if not await repo.set_pid(run.id, spawned.pid, spawned.started_at):
                raise ConflictError(HALTED)  # a halt ended the row while the process started
            await repo.change(run.id, instructions=launch.digest, memory_digest=digest)
        await self._ports.teams.attach_run(facts.id, run.id)
        begin.attached = True
        await self._ports.tickets.record_event(
            facts.id,
            "run.started",
            run.id,
            {"run": run.id, "stage": run.stage, "agent": run.agent, "model": run.model},
            self._clock(),
        )
        async with self._uow() as session:
            started = await RunRepository(session).get(run.id)
        assert started is not None  # noqa: S101  # inserted above in this call
        return started

    async def _abandon(
        self, begin: _Start, failure: BaseException, *, release_claim: bool = True
    ) -> None:
        """Undo what a failed start made: the process, the row, the token, the tree and the claim.

        A tree the start found stays, with the work it holds; so does a branch the ticket had.
        """
        run = begin.run
        if run is not None:
            if begin.spawned is not None:
                target = Target(begin.spawned.pid, begin.spawned.started_at, self.exit_path(run.id))
                await self._registry.stop(target)
            async with self._uow() as session:
                await RunRepository(session).end(
                    run.id,
                    RunEnd(exit_code=UNKNOWN, ended_at=self._clock(), halted=_reason(failure)),
                )
            await self._ports.tokens.revoke(run.id)
        if begin.tree is not None and begin.tree.made:
            await self._remove_made(begin)
        if release_claim:
            under = run.id if run is not None and begin.attached else None
            await self._ports.teams.end_claim(begin.facts.id, under)

    async def _remove_made(self, begin: _Start) -> None:
        """Remove the tree the start made, and the branch it gave the ticket on its first attempt.

        A removal that fails is logged: it must not hide why the start failed.
        """
        facts, tree = begin.facts, begin.tree
        assert tree is not None  # noqa: S101  # the caller checked
        try:
            await self._ports.trees.remove(facts.repository, tree)
            if begin.options.attempt == 0 and not facts.branch:
                await self._ports.tickets.clear_branch(facts.id)
        except CodeFactoryError:
            logger.warning("the tree of a failed start of %s stays", facts.id, exc_info=True)


def _reason(failure: BaseException) -> str:
    return str(failure) or type(failure).__name__
