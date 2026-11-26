"""Connections: their writes, their status and the environment a run on one is given."""

import asyncio
from typing import Any

from pydantic import SecretStr

from code_factory.agents.models.agents import AgentDefinition
from code_factory.agents.models.answers import (
    Changed,
    ConnectionList,
    ConnectionStatus,
    ConnectionView,
    RunConnection,
    UndoStep,
)
from code_factory.agents.models.connections import (
    ConnectionChange,
    ConnectionDefinition,
    Found,
    Status,
)
from code_factory.agents.models.constants import CODEX_LOGIN
from code_factory.agents.repository import AgentRepository, ConnectionRepository, RosterLock
from code_factory.agents.rules.connections import (
    KINDS,
    agent_refusal,
    apply_connection_change,
    rules,
    runs_here,
)
from code_factory.agents.rules.environment import Variables, codex_config, run_environment
from code_factory.agents.rules.login import login_reach
from code_factory.agents.rules.probes import reach
from code_factory.agents.service import undo as inverse
from code_factory.agents.service.base import Shared
from code_factory.platform.db import AsyncSession
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError

NO_CONNECTION = "no such connection"


def _blank() -> ConnectionDefinition:
    return ConnectionDefinition(name="", kind="custom", base_url="")


def _conn(raw: dict[str, Any] | None) -> ConnectionDefinition:
    assert raw is not None  # noqa: S101  # the step was built with it
    return ConnectionDefinition.model_validate(raw)


class ConnectionsService(Shared):
    """The model connections of this machine and the keys they name."""

    async def list_connections(self) -> ConnectionList:
        """Every connection with whether its key is set; never the key."""
        async with self._uow() as session:
            known = await ConnectionRepository(session).all()
        views = [
            ConnectionView(
                connection=c,
                key_set=bool(c.key_env) and await self._store.has(c.key_env),
                here=runs_here(c),
            )
            for c in known
        ]
        return ConnectionList(connections=views, kinds=KINDS)

    async def add_connection(self, change: ConnectionChange) -> Changed:
        """Add a connection at the end of the list."""
        async with self._uow() as session:
            await RosterLock(session).take()
            repo = ConnectionRepository(session)
            made = apply_connection_change(_blank(), change)
            if any(c.name == made.name for c in await repo.all()):
                raise ConflictError(f"a connection named {made.name} is defined")
            await repo.add(made)
        return Changed(
            notice=f"Added {made.name}",
            undo=inverse.step(inverse.CONNECTION_ADD, after=inverse.dump(made)),
        )

    async def edit_connection(self, name: str, change: ConnectionChange) -> Changed:
        """Change the connection `name`; agents that use it follow it, whatever its name."""
        async with self._uow() as session:
            await RosterLock(session).take()
            repo = ConnectionRepository(session)
            known = await repo.all()
            before = next((c for c in known if c.name == name), None)
            if before is None:
                raise NotFoundError(NO_CONNECTION)
            after = apply_connection_change(before, change)
            if after.name != name and any(c.name == after.name for c in known):
                raise ConflictError(f"a connection named {after.name} is defined")
            await self._agents_still_fit(session, name, after)
            await repo.replace(name, after)
            if (before.kind, before.base_url) != (after.kind, after.base_url):
                await AgentRepository(session).drop_checks_using(after.name)
        return Changed(
            notice=f"Saved {after.name}",
            undo=inverse.step(
                inverse.CONNECTION_REPLACE, before=inverse.dump(before), after=inverse.dump(after)
            ),
        )

    async def _agents_still_fit(
        self, session: AsyncSession, name: str, after: ConnectionDefinition
    ) -> None:
        for agent in await AgentRepository(session).all():
            if agent.connection == name:
                moved = agent.model_copy(update={"connection": after.name})
                if (why := agent_refusal(moved, [after])) is not None:
                    raise BadRequestError(why)

    async def remove_connection(self, name: str) -> Changed:
        """Remove the connection `name`, refused while an agent uses it."""
        async with self._uow() as session:
            await RosterLock(session).take()
            repo = ConnectionRepository(session)
            known = await repo.all()
            before = next((c for c in known if c.name == name), None)
            if before is None:
                raise NotFoundError(NO_CONNECTION)
            if (user := await AgentRepository(session).uses_connection(name)) is not None:
                raise ConflictError(f"agent {user} uses connection {name}")
            await repo.remove(name)
        index = next(i for i, c in enumerate(known) if c.name == name)
        return Changed(
            notice=f"Removed {name}",
            undo=inverse.step(inverse.CONNECTION_REMOVE, before=inverse.dump(before), index=index),
        )

    async def undo_connection(self, step: UndoStep) -> None:
        """Apply the inverse of a connection write; `ConflictError` when it changed since."""
        async with self._uow() as session:
            await RosterLock(session).take()
            repo = ConnectionRepository(session)
            known = {c.name: c for c in await repo.all()}
            payload = step.payload
            if step.kind == inverse.CONNECTION_ADD:
                after = _conn(payload["after"])
                if known.get(after.name) != after:
                    raise inverse.changed_since(after.name)
                if await AgentRepository(session).uses_connection(after.name) is not None:
                    raise ConflictError(f"connection {after.name} is in use; nothing was undone")
                await repo.remove(after.name)
            elif step.kind == inverse.CONNECTION_REMOVE:
                before = _conn(payload["before"])
                if before.name in known:
                    raise ConflictError(f"a connection named {before.name} is defined")
                await repo.add(before, payload["index"])
            else:
                before, after = _conn(payload["before"]), _conn(payload["after"])
                if known.get(after.name) != after:
                    raise inverse.changed_since(after.name)
                if before.name != after.name and before.name in known:
                    raise ConflictError(f"a connection named {before.name} is defined")
                await self._agents_still_fit(session, after.name, before)
                await repo.replace(after.name, before)
                await AgentRepository(session).drop_checks_using(before.name)

    async def _key_for(self, connection: ConnectionDefinition) -> SecretStr | None:
        return await self._store.read(connection.key_env) if connection.key_env else None

    async def _status_of(self, connection: ConnectionDefinition) -> Status:
        if connection.kind == CODEX_LOGIN:
            try:
                rules(connection)
            except BadRequestError as why:
                return Status(name=connection.name, answers=False, problem=str(why))
            return await self._codex_catalog(connection.name)
        return await self._probe.status(connection, await self._key_for(connection))

    async def connection_status(self) -> ConnectionStatus:
        """Whether each connection answers, the local servers found, and each agent's reach."""
        async with self._uow() as session:
            known = await ConnectionRepository(session).all()
            agents = await AgentRepository(session).all()
        async with asyncio.TaskGroup() as group:
            local = group.create_task(self._probe.local())
            asked = [group.create_task(self._guarded(c)) for c in known]
        statuses = [task.result() for task in asked]
        return ConnectionStatus(
            connections=statuses,
            local=_found(local),
            reach=_reach(agents, known, statuses),
        )

    async def _guarded(self, connection: ConnectionDefinition) -> Status:
        """One connection's status; a failure of its probe is that connection's problem alone."""
        try:
            return await self._status_of(connection)
        except Exception as error:  # noqa: BLE001  # one probe must not end the others
            return Status(name=connection.name, answers=False, problem=type(error).__name__)

    async def run_connection(
        self, name: str, model: str, runtime: str = "claude", *, broker: int | None = None
    ) -> RunConnection:
        """What a run of an agent on connection `name` is started with."""
        async with self._uow() as session:
            known = await ConnectionRepository(session).all()
        connection = next((c for c in known if c.name == name), None)
        if connection is None:
            raise NotFoundError(NO_CONNECTION)
        key = await self._key_for(connection)
        if runtime == "codex":
            text, selector = codex_config(connection, model, key, broker)
            return RunConnection(env={}, config_env=text, selector=selector)
        env: Variables = run_environment(connection, model, key)
        return RunConnection(env=env, selector=model)


def _found(task: asyncio.Task[list[Found]]) -> list[Found]:
    return task.result()


def _reach(
    agents: list[AgentDefinition], known: list[ConnectionDefinition], statuses: list[Status]
) -> dict[str, str]:
    by_name = {c.name: (c, s) for c, s in zip(known, statuses, strict=True)}
    words: dict[str, str] = {}
    for agent in agents:
        pair = by_name.get(agent.connection)
        if pair is None:
            continue
        connection, status = pair
        words[agent.name] = (
            login_reach(status)
            if connection.kind == CODEX_LOGIN and not status.answers
            else reach(agent.model, status)
        )
    return words
