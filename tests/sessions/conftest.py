"""Fixtures of the sessions tests."""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sample_world import World, build_world, write_sample_spool
from sessions_harness import TABLES, Clock, Committed
from sqlalchemy import text

from code_factory.platform.config import Settings
from code_factory.platform.db import (
    AsyncEngine,
    UnitOfWork,
    create_engine,
    create_session_factory,
)
from code_factory.sessions.repository import ListenConnection, channel_for
from code_factory.sessions.service import SessionService


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "state"
    folder.mkdir()
    return folder


@pytest.fixture
def sessions(uow: UnitOfWork, state_dir: Path, clock: Clock) -> SessionService:
    """The service on the isolated connection, its clock at the sample's moment."""
    return SessionService(uow, state_dir=state_dir, clock=clock)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return build_world(tmp_path / "world")


@pytest.fixture
def sample(world: World, state_dir: Path) -> World:
    """The sample's spool written into the state folder."""
    write_sample_spool(state_dir / "spool", world)
    return world


@pytest.fixture
async def committed(settings: Settings, migrated: None) -> AsyncGenerator[Committed]:  # noqa: ARG001
    """Services on connections of their own that really commit: the tables are emptied around it.

    For what the savepoint fixtures cannot show: two ingesters at once, notifications, a listener.
    """
    engines: list[AsyncEngine] = []

    def make(state_dir: Path, **options: object) -> SessionService:
        engine = create_engine(settings)
        engines.append(engine)
        dsn = settings.database_url.get_secret_value().replace("+asyncpg", "", 1)
        return SessionService(
            UnitOfWork(create_session_factory(engine)),
            state_dir=state_dir,
            listen_dsn=dsn,
            schema=settings.db_schema,
            **options,  # ty: ignore[invalid-argument-type]  # the service's own options
        )

    admin = create_engine(settings)
    engines.append(admin)

    async def empty() -> None:
        async with admin.begin() as connection:
            await connection.execute(text(f"truncate {', '.join(TABLES)} restart identity"))

    await empty()
    try:
        yield Committed(
            make, admin, ListenConnection.application_name(channel_for(settings.db_schema))
        )
    finally:
        await empty()
        for engine in engines:
            await engine.dispose()
