"""Shared fixtures.

Database isolation: every test runs inside one outer transaction on one connection and the
sessions the app opens are bound to that connection with `join_transaction_mode="create_savepoint"`.
The app's own `commit()` releases a savepoint, the outer transaction is rolled back after the
test, so nothing persists and no table is truncated (the migration seeds `schema_info`, which a
truncate would delete). The schema itself is built once per session by `alembic upgrade head`.

Under pytest-xdist each worker gets a schema of its own inside the one test database
(`CODE_FACTORY_DB_SCHEMA=test_<run>_<worker>`, set before anything reads the settings), built and
dropped by `migrated`, so workers never see each other's rows and tests that migrate down and up
are safe.

Tests that need no database use `offline_app`: the lifespan is not run, so nothing connects.
"""

import asyncio
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app_lifespan import DB_SCHEMA_VARIABLE, IDLE_MODULES, running_lifespan
from code_factory.app import create_app
from code_factory.memory.service import MemoryService
from code_factory.platform.config import DATABASE_URL_VARIABLE, Settings, load_settings
from code_factory.platform.db import (
    UnitOfWork,
    create_engine,
    create_schema,
    drop_schema,
)
from code_factory.platform.db.engine import DATABASE_ERRORS
from code_factory.platform.db.migrate import upgrade
from code_factory.repositories.service import RepositoryService
from code_factory.tickets.models import NewTicket, Ticket
from code_factory.tickets.service import (
    ActivityService,
    DocumentService,
    ReviewService,
    TicketService,
)
from database_guard import UnsafeDatabaseError, assert_test_database
from isolated_sessions import isolated_sessions
from memory_values import NOW as MEMORY_NOW
from ticket_values import NOW as TICKETS_NOW
from ticket_values import OWNER

# The git fixtures are in tests/git_fixtures.py, the memory-extras bench in
# tests/memory_extras_bench.py, the metrics fixtures in tests/metrics_fixtures.py.
pytest_plugins = [
    "pytester",
    "board_template",
    "git_fixtures",
    "memory_extras_bench",
    "metrics_fixtures",
]

# Tests must not inherit a developer's env files: Settings reads them from the working directory, so
# a local `.env.local` would change what passes here and in CI. The process environment still
# applies, which is how the gate supplies the database URL. Tests of the files turn them on.
Settings.model_config["env_file"] = None

OFFLINE_URL = "postgresql+asyncpg://nobody:not-a-password@127.0.0.1:1/never_connected"


def _is_xdist_controller(config: pytest.Config) -> bool:
    return bool(config.getoption("numprocesses", None)) and not hasattr(config, "workerinput")


def pytest_configure(config: pytest.Config) -> None:
    """Refuse the whole session when the environment points at a non-test database.

    An xdist worker also moves to its own schema, so it must do so before any settings load; the
    controller fixes the run id first, so it can drop what the workers built if they are stopped.
    """
    if _is_xdist_controller(config) and config.getoption("testrunuid", None) is None:
        config.option.testrunuid = uuid.uuid4().hex
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker is not None:
        # The run id keeps two pytest runs on one database (a subset beside the gate) apart.
        run = os.environ["PYTEST_XDIST_TESTRUNUID"]
        os.environ[DB_SCHEMA_VARIABLE] = f"test_{run}_{worker}"
    url = os.environ.get(DATABASE_URL_VARIABLE)
    if url is not None:
        try:
            assert_test_database(url)
        except UnsafeDatabaseError as error:
            pytest.exit(str(error), returncode=2)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Drop the worker schemas of this run: workers stopped by Ctrl-C never run their teardown.

    Best effort: the workers' own teardown is the first line, and a database that is down must not
    turn an offline run into an error. The guard applies again here, since pytest calls this hook
    even when `pytest_configure` refused the database.
    """
    url = os.environ.get(DATABASE_URL_VARIABLE)
    if url is None or not _is_xdist_controller(config):
        return
    try:
        assert_test_database(url)
        pattern = f"test\\_{config.getoption('testrunuid')}\\_%"
        asyncio.run(_drop_schemas_like(load_settings(), pattern))
    except UnsafeDatabaseError:
        return
    except (OSError, *DATABASE_ERRORS):
        sys.stderr.write(
            "conftest: could not drop this run's worker schemas; the database did not answer\n"
        )


async def _drop_schemas_like(settings: Settings, pattern: str) -> None:
    engine = create_engine(settings)
    try:
        async with engine.begin() as connection:
            found = await connection.execute(
                text("SELECT nspname FROM pg_namespace WHERE nspname LIKE :pattern"),
                {"pattern": pattern},
            )
            for (name,) in found.all():
                await connection.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Settings from the environment, which the gate points at `code_factory_test`."""
    if DATABASE_URL_VARIABLE not in os.environ:
        pytest.exit(
            f"{DATABASE_URL_VARIABLE} is not set; run tests through scripts/gate.sh, which "
            "builds it from the keychain",
            returncode=2,
        )
    return Settings(_env_file=None)


@pytest.fixture(scope="session")
def migrated(settings: Settings) -> Iterator[None]:
    """The test database at head, built by Alembic (never `create_all`).

    A worker's schema is built from nothing and dropped at the end; without xdist the configured
    schema (the default one unless the caller set it) is migrated in place and left alone.
    """
    own_schema = "PYTEST_XDIST_WORKER" in os.environ
    if own_schema:
        asyncio.run(drop_schema(settings))
        asyncio.run(create_schema(settings))
    try:
        upgrade()
        yield
    finally:
        if own_schema:
            asyncio.run(drop_schema(settings))


@pytest.fixture
async def serve_env(settings: Settings, migrated: None) -> AsyncGenerator[dict[str, str]]:  # noqa: ARG001
    """The environment for a real `serve` process: a schema of its own, migrated, dropped after.

    A served board writes (its sign-in value), and rows in the shared schema would show in tests
    that count rows.
    """
    schema = f"serve_{uuid.uuid4().hex[:10]}"
    env = {**os.environ, "CODE_FACTORY_DB_SCHEMA": schema}
    admin = create_engine(settings)
    try:
        async with admin.begin() as admin_connection:
            await admin_connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        # Alembic starts its own event loop, so it runs in a thread with this environment.
        await asyncio.to_thread(_upgrade_in, env)
        yield env
    finally:
        async with admin.begin() as admin_connection:
            await admin_connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def _upgrade_in(env: dict[str, str]) -> None:
    subprocess.run(  # noqa: S603  # our own console script, no shell
        [str(Path(sys.executable).parent / "code-factory"), "db", "upgrade"],
        env=env,
        check=True,
        capture_output=True,
    )


@pytest.fixture
async def connection(settings: Settings, migrated: None) -> AsyncGenerator[AsyncConnection]:  # noqa: ARG001
    """A connection inside an outer transaction that is rolled back after the test."""
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                yield connection
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
def uow(connection: AsyncConnection) -> UnitOfWork:
    """What a service is built with: units of work on the isolated connection."""
    return UnitOfWork(isolated_sessions(connection))


@pytest.fixture
async def db_session(connection: AsyncConnection) -> AsyncGenerator[AsyncSession]:
    """A session on the isolated connection."""
    async with isolated_sessions(connection)() as session:
        yield session


@pytest.fixture
def offline_settings() -> Settings:
    """Settings that point nowhere; for tests that never run the lifespan."""
    return Settings(database_url=OFFLINE_URL, _env_file=None)


@pytest.fixture
def offline_app(offline_settings: Settings) -> FastAPI:
    """The app without its lifespan."""
    return create_app(offline_settings, guarded=False)


@pytest.fixture
async def offline_client(offline_app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    """A client over ASGI; the lifespan does not run, so no database is touched."""
    transport = httpx.ASGITransport(app=offline_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        yield client


@pytest.fixture
async def app(settings: Settings, connection: AsyncConnection) -> AsyncGenerator[FastAPI]:
    """The app with its lifespan running and its sessions on the isolated connection."""
    application = create_app(
        settings, isolated_sessions(connection), guarded=False, modules=IDLE_MODULES
    )
    async with running_lifespan(application):
        yield application


@pytest.fixture
async def guarded_client(
    settings: Settings, connection: AsyncConnection
) -> AsyncGenerator[httpx.AsyncClient]:
    """A client of the app as `serve` builds it: the sign-in guard on."""
    application = create_app(settings, isolated_sessions(connection), modules=IDLE_MODULES)
    async with (
        running_lifespan(application),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://127.0.0.1"
        ) as client,
    ):
        yield client


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    """A client over ASGI against the app with its lifespan running."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    ) as client:
        yield client


@pytest.fixture
def tickets(uow: UnitOfWork) -> TicketService:
    """The ticket service on the isolated connection, its clock at `ticket_values.NOW`."""
    return TicketService(uow, clock=lambda: TICKETS_NOW)


@pytest.fixture
def activity(uow: UnitOfWork) -> ActivityService:
    return ActivityService(uow, clock=lambda: TICKETS_NOW)


@pytest.fixture
def documents(uow: UnitOfWork) -> DocumentService:
    return DocumentService(uow, clock=lambda: TICKETS_NOW)


@pytest.fixture
def reviews(uow: UnitOfWork) -> ReviewService:
    return ReviewService(uow, clock=lambda: TICKETS_NOW)


@pytest.fixture
async def ticket(tickets: TicketService) -> Ticket:
    """A fresh ticket in the `sample` repository."""
    return await tickets.create(NewTicket(repository="sample", title="A ticket"), by=OWNER)


@pytest.fixture
def memory(uow: UnitOfWork) -> MemoryService:
    """The memory service on the isolated connection, its clock at `memory_values.NOW`."""
    return MemoryService(uow, clock=lambda: MEMORY_NOW)


@pytest.fixture
def repositories(uow: UnitOfWork) -> RepositoryService:
    """The repositories service on the isolated connection."""
    return RepositoryService(uow)
