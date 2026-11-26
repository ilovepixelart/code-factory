"""The four tables, their constraints and the revision that creates them, against PostgreSQL."""

from datetime import UTC, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from code_factory.agents.tables import AgentRow, ConnectionRow
from code_factory.platform.db import Base

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
TABLES = {"connections", "agents", "agent_context_versions", "agent_model_checks"}


def _agents_diff(sync_connection: Connection) -> list[object]:
    context = MigrationContext.configure(sync_connection)
    return [
        change
        for change in compare_metadata(context, Base.metadata)
        if TABLES & set(str(change).replace("'", " ").replace(",", " ").split())
    ]


async def test_the_models_and_the_revision_agree(connection: AsyncConnection) -> None:
    assert await connection.run_sync(_agents_diff) == []


async def test_no_column_can_hold_a_provider_key(connection: AsyncConnection) -> None:
    found = await connection.execute(
        text(
            "select column_name from information_schema.columns "
            "where table_schema = current_schema() and table_name = 'connections' "
            "order by ordinal_position"
        )
    )
    assert [name for (name,) in found] == [
        "id",
        "position",
        "name",
        "kind",
        "base_url",
        "key_name",
        "management_key_name",
        "created_at",
        "updated_at",
    ]


async def fails(session: AsyncSession, row: object) -> str:
    session.add(row)
    with pytest.raises(IntegrityError) as caught:
        await session.flush()
    await session.rollback()
    return str(caught.value.orig)


def agent(**fields: object) -> AgentRow:
    return AgentRow(**{"position": 1, "name": "a", "runtime": "claude", **fields})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"name": "-a"}, "ck_agents_name"),
        ({"name": "a\n"}, "ck_agents_name"),
        ({"name": "x" * 41}, "ck_agents_name"),
        ({"runtime": "pi"}, "ck_agents_runtime"),
        ({"roles": ["spec", "x"]}, "ck_agents_roles"),
        ({"max_tokens": 0}, "ck_agents_max_tokens"),
        ({"max_seconds": 0}, "ck_agents_max_seconds"),
        ({"input_price": 1.0}, "ck_agents_prices_together"),
        ({"input_price": -1.0, "output_price": 1.0}, "ck_agents_prices"),
        ({"input_price": float("nan"), "output_price": 1.0}, "ck_agents_prices"),
        ({"max_daily_usd": 0.0}, "ck_agents_max_daily_usd"),
        ({"max_daily_usd": float("inf")}, "ck_agents_max_daily_usd"),
        ({"context": "x" * 8001, "context_at": NOW}, "ck_agents_context_length"),
        ({"context": "x"}, "ck_agents_context_time"),
        ({"context_at": NOW}, "ck_agents_context_time"),
    ],
)
async def test_a_row_off_the_model_is_refused_by_the_database_too(
    db_session: AsyncSession, fields: dict[str, object], constraint: str
) -> None:
    assert constraint in await fails(db_session, agent(**fields))


async def test_the_limits_of_the_model_are_accepted(db_session: AsyncSession) -> None:
    db_session.add(agent(name="x" * 40, context="x" * 8000, context_at=NOW, roles=["spec"]))
    db_session.add(agent(name="b", position=2, input_price=0.0, output_price=0.0))
    await db_session.flush()


async def test_a_name_is_taken_once(db_session: AsyncSession) -> None:
    db_session.add(agent())
    await db_session.flush()
    assert "uq_agents_name" in await fails(db_session, agent(position=2))


async def test_a_used_connection_cannot_be_deleted_and_its_agent_cannot_name_a_missing_one(
    db_session: AsyncSession,
) -> None:
    link = ConnectionRow(position=1, name="c", kind="ollama", base_url="http://localhost:11434")
    db_session.add(link)
    await db_session.flush()
    db_session.add(agent(connection_id=link.id))
    await db_session.flush()
    with pytest.raises(IntegrityError) as caught:
        await db_session.execute(text("delete from connections"))
    assert "fk_agents_connection_id_connections" in str(caught.value.orig)
    await db_session.rollback()


async def test_deleting_an_agent_deletes_its_versions_and_its_check(
    db_session: AsyncSession,
) -> None:
    row = agent()
    db_session.add(row)
    await db_session.flush()
    await db_session.execute(
        text("insert into agent_context_versions (agent_id, at, context) values (:a, now(), 'x')"),
        {"a": row.id},
    )
    await db_session.execute(
        text(
            "insert into agent_model_checks (agent_id, runtime, connection, model, passed, "
            "checked_at) values (:a, 'claude', '', 'm', true, now())"
        ),
        {"a": row.id},
    )
    await db_session.execute(text("delete from agents"))
    versions = await db_session.execute(text("select count(*) from agent_context_versions"))
    checks = await db_session.execute(text("select count(*) from agent_model_checks"))
    assert (versions.scalar(), checks.scalar()) == (0, 0)


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"name": "bad name"}, "ck_connections_name"),
        ({"kind": "nope"}, "ck_connections_kind"),
    ],
)
async def test_a_connection_off_the_model_is_refused(
    db_session: AsyncSession, fields: dict[str, object], constraint: str
) -> None:
    row = ConnectionRow(
        **{"position": 1, "name": "c", "kind": "ollama", "base_url": "x", **fields}  # type: ignore[arg-type]
    )
    assert constraint in await fails(db_session, row)
