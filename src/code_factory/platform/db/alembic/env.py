"""Alembic environment: the async recipe from the Alembic cookbook, "Using asyncio with Alembic".

The connection is async; `run_sync` hands Alembic a synchronous view of it. The URL comes from
the application settings, never from `alembic.ini`.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

import code_factory.app  # noqa: F401  # imports every module's tables into Base.metadata
from code_factory.platform.config import load_settings
from code_factory.platform.db import Base
from code_factory.platform.db.migrate import create_migration_engine

config = context.config
if config.config_file_name is not None:
    # Keep the application's own loggers (they are configured by `setup_logging`).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    """Run the migrations on a synchronous view of the async connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # One transaction per migration: Postgres runs DDL transactionally, so a failed
        # migration leaves neither half its changes nor a stale version row.
        transaction_per_migration=True,
        version_table=config.get_main_option("version_table", "alembic_version"),
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Open the async connection and run the migrations on it."""
    engine = create_migration_engine(load_settings())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_offline() -> None:
    """Offline mode (SQL script output) is not supported: the settings hold the URL."""
    msg = "offline migrations are not supported; run `code-factory db upgrade`"
    raise RuntimeError(msg)


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
