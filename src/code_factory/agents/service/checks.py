"""Model checks, the start refusals they and a connection's state give, and agent resolution."""

import asyncio

from code_factory.agents.models.agents import AgentDefinition, epoch
from code_factory.agents.models.answers import AgentFacts, ResolvedAgent, Setup
from code_factory.agents.models.checks import ModelCheck
from code_factory.agents.models.connections import ConnectionDefinition
from code_factory.agents.models.constants import CODEX_LOGIN
from code_factory.agents.repository import AgentRepository, ConnectionRepository, RosterLock
from code_factory.agents.rules.connections import runs_here
from code_factory.agents.rules.model_checks import (
    check_requests,
    check_target,
    current,
    run_refusal,
    verdict,
)
from code_factory.agents.rules.probes import context_refusal
from code_factory.agents.rules.roster import setup_for
from code_factory.agents.service.base import Shared
from code_factory.platform.errors import ConflictError, NotFoundError

NO_AGENT = "no such agent"


class ChecksService(Shared):
    """Tests an agent's model and says whether a run may start on it."""

    async def _read(self, name: str) -> tuple[AgentDefinition, list[ConnectionDefinition]]:
        async with self._uow() as session:
            agent = await AgentRepository(session).get(name)
            connections = await ConnectionRepository(session).all()
        if agent is None:
            raise NotFoundError(NO_AGENT)
        return agent, connections

    async def check_model(self, name: str) -> ModelCheck:
        """Test the agent's model with one tool call and one JSON answer, and keep the result.

        The transaction is released while the model answers; the result is kept only when the
        agent still has the runtime, connection and model it was taken with.
        """
        lock = self._check_locks.setdefault(name, asyncio.Lock())
        async with lock, self._checks_at_once:
            agent, connections = await self._read(name)
            target = check_target(agent, connections)
            problem = await self._problem(agent, target)
            result = ModelCheck(
                runtime=agent.runtime,
                connection=agent.connection,
                model=agent.model,
                passed=problem is None,
                problem=problem or "",
                at=self._clock().replace(microsecond=0),
            )
            async with self._uow() as session:
                await RosterLock(session).take()
                repo = AgentRepository(session)
                now = await repo.get(name)
                connections_now = await ConnectionRepository(session).all()
                if (
                    now is None
                    or (now.runtime, now.connection, now.model)
                    != (agent.runtime, agent.connection, agent.model)
                    or target not in connections_now
                ):
                    raise ConflictError(
                        f"agent {name} changed while its model was checked; nothing was kept"
                    )
                await repo.put_check(name, result)
            return result

    async def _problem(self, agent: AgentDefinition, target: ConnectionDefinition) -> str | None:
        tool, answer = check_requests(agent.runtime, target, agent.model)
        for request in (tool, answer):
            heard = await self._probe.ask(request)
            why = verdict(agent.runtime, target.kind, agent.model, request.ask, heard)
            if why is not None:
                return why
        return None

    async def model_checks(self) -> dict[str, ModelCheck]:
        """Each agent's current check, by name."""
        async with self._uow() as session:
            repo = AgentRepository(session)
            agents, checks = await repo.all(), await repo.checks()
        return {a.name: kept for a in agents if (kept := current(checks.get(a.name), a))}

    async def run_refusal(self, name: str) -> str | None:
        """Why a run of the agent may not start; None when it may.

        A failed check, a context under 64,000, an unlisted model or a missing codex login.
        """
        agent, connections = await self._read(name)
        async with self._uow() as session:
            check = (await AgentRepository(session).checks()).get(name)
        if (why := run_refusal(check, agent)) is not None:
            return why
        connection = next((c for c in connections if c.name == agent.connection), None)
        if connection is None:
            return None
        if connection.kind == CODEX_LOGIN:
            return await self._codex_refusal(connection.name, agent.model)
        if runs_here(connection) and agent.model:
            status = await self._probe.status(connection, None)
            return context_refusal(connection.kind, status, agent.model)
        return None

    async def _codex_refusal(self, connection: str, model: str) -> str | None:
        catalog = await self._codex_catalog(connection)
        if not catalog.answers:
            return f"connection {connection}: could not validate the model ({catalog.problem})"
        if model not in {entry.id for entry in catalog.models}:
            return (
                f"connection {connection}: {model or 'no model is set'}; "
                "choose a model available to this Codex login in Agents"
            )
        return None

    async def resolve_agent(
        self,
        name: str | None,
        *,
        stand_in: str = "",
        repository_template: str = "",
        repository_model: str = "",
    ) -> ResolvedAgent:
        """The agent a run starts as, its connection and setup; the default agent for no name."""
        if name is None or name == "":
            template, model = setup_for(None, stand_in, repository_template, repository_model)
            return ResolvedAgent(
                definition=None,
                connection=None,
                setup=Setup(agent="", template=template, model=model, connection=""),
            )
        agent, connections = await self._read(name)
        template, model = setup_for(agent, stand_in, repository_template, repository_model)
        connection = next((c for c in connections if c.name == agent.connection), None)
        return ResolvedAgent(
            definition=agent,
            connection=connection,
            setup=Setup(
                agent=agent.name, template=template, model=model, connection=agent.connection
            ),
        )

    async def team_agents(self) -> list[AgentFacts]:
        """Every agent as the team reads it; `refusal` is a failed check's sentence."""
        async with self._uow() as session:
            repo = AgentRepository(session)
            agents, checks = await repo.all(), await repo.checks()
        return [
            AgentFacts(
                name=a.name,
                roles=tuple(a.roles),
                types=tuple(a.types),
                labels=tuple(a.labels),
                max_tokens=a.max_tokens,
                max_seconds=a.max_seconds,
                input_price=a.input_price,
                output_price=a.output_price,
                max_daily_usd=a.max_daily_usd,
                paused_at=None if a.paused_at is None else float(epoch(a.paused_at)),
                runtime=a.runtime,
                connection=a.connection,
                model=a.model,
                refusal=run_refusal(checks.get(a.name), a) or "",
            )
            for a in agents
        ]
