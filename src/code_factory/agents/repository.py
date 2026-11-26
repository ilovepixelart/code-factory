"""Queries on the agents tables, over the session of one unit of work.

Every write of the roster takes `lock` first (one transaction-scoped advisory lock) and reads the
rows it rewrites after it, so two writes never interleave their positions.
"""

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from code_factory.agents.models.agents import AgentDefinition, ContextVersion
from code_factory.agents.models.checks import ModelCheck
from code_factory.agents.models.connections import ConnectionDefinition
from code_factory.agents.tables import AgentRow, ConnectionRow, ContextVersionRow, ModelCheckRow
from code_factory.platform.db import AsyncSession, lock_until_commit
from code_factory.platform.errors import NotFoundError


class RosterLock:
    """The advisory lock that serialises every write of agents, connections and checks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def take(self) -> None:
        """Wait for the lock; it is released when the transaction ends."""
        await lock_until_commit(self._session, "agents")


def _definition(
    row: AgentRow, connection: str | None, versions: list[ContextVersion]
) -> AgentDefinition:
    return AgentDefinition(
        name=row.name,
        runtime=row.runtime,
        connection=connection or "",
        model=row.model,
        roles=list(row.roles),
        types=list(row.types),
        labels=list(row.labels),
        max_tokens=row.max_tokens,
        max_seconds=row.max_seconds,
        input_price=row.input_price,
        output_price=row.output_price,
        max_daily_usd=row.max_daily_usd,
        paused_at=row.paused_at,
        context=row.context,
        context_at=row.context_at,
        context_history=versions,
    )


def _values(agent: AgentDefinition, connection_id: int | None) -> dict[str, object]:
    return {
        "name": agent.name,
        "runtime": agent.runtime,
        "connection_id": connection_id,
        "model": agent.model,
        "roles": agent.roles,
        "types": agent.types,
        "labels": agent.labels,
        "max_tokens": agent.max_tokens,
        "max_seconds": agent.max_seconds,
        "input_price": agent.input_price,
        "output_price": agent.output_price,
        "max_daily_usd": agent.max_daily_usd,
        "paused_at": agent.paused_at,
        "context": agent.context,
        "context_at": agent.context_at,
    }


class AgentRepository:
    """Agents with their context versions, in the order the board tries them."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self) -> list[AgentDefinition]:
        """Every agent, first in the order its columns are tried."""
        rows = (
            await self._session.execute(
                select(AgentRow, ConnectionRow.name)
                .outerjoin(ConnectionRow, AgentRow.connection_id == ConnectionRow.id)
                .order_by(AgentRow.position, AgentRow.id)
            )
        ).all()
        versions = await self._versions([row.id for row, _ in rows])
        return [_definition(row, name, versions.get(row.id, [])) for row, name in rows]

    async def get(self, name: str) -> AgentDefinition | None:
        """The agent named `name`, if any."""
        return next((agent for agent in await self.all() if agent.name == name), None)

    async def _versions(self, ids: list[int]) -> dict[int, list[ContextVersion]]:
        found = await self._session.scalars(
            select(ContextVersionRow)
            .where(ContextVersionRow.agent_id.in_(ids))
            .order_by(ContextVersionRow.at.desc(), ContextVersionRow.id)
        )
        grouped: dict[int, list[ContextVersion]] = {}
        for row in found:
            grouped.setdefault(row.agent_id, []).append(
                ContextVersion(at=row.at, context=row.context)
            )
        return grouped

    async def _connection_id(self, name: str) -> int | None:
        if not name:
            return None
        found = await self._session.scalar(
            select(ConnectionRow.id).where(ConnectionRow.name == name)
        )
        if found is None:
            msg = "no such connection"
            raise NotFoundError(msg)
        return found

    async def _id(self, name: str) -> int:
        found = await self._session.scalar(select(AgentRow.id).where(AgentRow.name == name))
        if found is None:
            msg = "no such agent"
            raise NotFoundError(msg)
        return found

    async def _put_versions(self, agent_id: int, versions: list[ContextVersion]) -> None:
        await self._session.execute(
            delete(ContextVersionRow).where(ContextVersionRow.agent_id == agent_id)
        )
        for version in versions:
            self._session.add(
                ContextVersionRow(agent_id=agent_id, at=version.at, context=version.context)
            )
        await self._session.flush()

    async def add(self, agent: AgentDefinition, index: int | None = None) -> None:
        """Insert `agent` at `index` among the agents (the end when None), with its versions."""
        names = [existing.name for existing in await self.all()]
        row = AgentRow(
            position=len(names) + 1, **_values(agent, await self._connection_id(agent.connection))
        )
        self._session.add(row)
        await self._session.flush()
        await self._put_versions(row.id, agent.context_history)
        names.insert(len(names) if index is None else index, agent.name)
        await self.reorder(names)

    async def replace(self, name: str, agent: AgentDefinition) -> None:
        """Rewrite the agent `name` with `agent`, its name and context versions included."""
        agent_id = await self._id(name)
        values = _values(agent, await self._connection_id(agent.connection))
        await self._session.execute(
            update(AgentRow).where(AgentRow.id == agent_id).values(**values, updated_at=func.now())
        )
        await self._put_versions(agent_id, agent.context_history)

    async def remove(self, name: str) -> None:
        """Delete the agent; its versions and its check go with it."""
        await self._session.execute(delete(AgentRow).where(AgentRow.name == name))

    async def reorder(self, names: list[str]) -> None:
        """Number the agents 1 to n in the order of `names`."""
        for place, name in enumerate(names, start=1):
            await self._session.execute(
                update(AgentRow).where(AgentRow.name == name).values(position=place)
            )

    async def uses_connection(self, connection: str) -> str | None:
        """The name of the first agent that uses `connection`, if any."""
        return await self._session.scalar(
            select(AgentRow.name)
            .join(ConnectionRow, AgentRow.connection_id == ConnectionRow.id)
            .where(ConnectionRow.name == connection)
            .order_by(AgentRow.position)
        )

    async def drop_checks_using(self, connection: str) -> None:
        """Forget the checks of the agents that use `connection`: its server may be another."""
        users = (
            select(AgentRow.id)
            .join(ConnectionRow, AgentRow.connection_id == ConnectionRow.id)
            .where(ConnectionRow.name == connection)
        )
        await self._session.execute(delete(ModelCheckRow).where(ModelCheckRow.agent_id.in_(users)))

    async def checks(self) -> dict[str, ModelCheck]:
        """Each agent's kept check, by agent name."""
        rows = await self._session.execute(
            select(AgentRow.name, ModelCheckRow).join(
                ModelCheckRow, ModelCheckRow.agent_id == AgentRow.id
            )
        )
        return {name: _check(row) for name, row in rows}

    async def put_check(self, name: str, check: ModelCheck) -> None:
        """Keep `check` as the agent's one current result, replacing an earlier one."""
        agent_id = await self._id(name)
        values = {
            "runtime": check.runtime,
            "connection": check.connection,
            "model": check.model,
            "passed": check.passed,
            "problem": check.problem,
            "checked_at": check.at,
        }
        statement = insert(ModelCheckRow).values(agent_id=agent_id, **values)
        await self._session.execute(
            statement.on_conflict_do_update(index_elements=[ModelCheckRow.agent_id], set_=values)
        )


def _check(row: ModelCheckRow) -> ModelCheck:
    return ModelCheck(
        runtime=row.runtime,
        connection=row.connection,
        model=row.model,
        passed=row.passed,
        problem=row.problem,
        at=row.checked_at,
    )


def _connection(row: ConnectionRow) -> ConnectionDefinition:
    return ConnectionDefinition(
        name=row.name,
        kind=row.kind,
        base_url=row.base_url,
        key_env=row.key_name,
        management_key_env=row.management_key_name,
    )


class ConnectionRepository:
    """Connections, in the order the page lists them."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self) -> list[ConnectionDefinition]:
        """Every connection in its order."""
        rows = await self._session.scalars(
            select(ConnectionRow).order_by(ConnectionRow.position, ConnectionRow.id)
        )
        return [_connection(row) for row in rows]

    async def add(self, connection: ConnectionDefinition, index: int | None = None) -> None:
        """Insert `connection` at `index` among the connections (the end when None)."""
        names = [existing.name for existing in await self.all()]
        self._session.add(
            ConnectionRow(
                position=len(names) + 1,
                name=connection.name,
                kind=connection.kind,
                base_url=connection.base_url,
                key_name=connection.key_env,
                management_key_name=connection.management_key_env,
            )
        )
        await self._session.flush()
        names.insert(len(names) if index is None else index, connection.name)
        await self.reorder(names)

    async def replace(self, name: str, connection: ConnectionDefinition) -> None:
        """Rewrite the connection `name`; the agents that use it follow by id."""
        await self._session.execute(
            update(ConnectionRow)
            .where(ConnectionRow.name == name)
            .values(
                name=connection.name,
                kind=connection.kind,
                base_url=connection.base_url,
                key_name=connection.key_env,
                management_key_name=connection.management_key_env,
                updated_at=func.now(),
            )
        )

    async def remove(self, name: str) -> None:
        """Delete the connection; the database refuses while an agent uses it."""
        await self._session.execute(delete(ConnectionRow).where(ConnectionRow.name == name))

    async def reorder(self, names: list[str]) -> None:
        """Number the connections 1 to n in the order of `names`."""
        for place, name in enumerate(names, start=1):
            await self._session.execute(
                update(ConnectionRow).where(ConnectionRow.name == name).values(position=place)
            )
