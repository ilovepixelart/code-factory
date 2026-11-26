"""Run the Alembic migrations bundled with the application."""

import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from code_factory.platform.config import Settings, load_settings
from code_factory.platform.db.engine import DATABASE_ERRORS, connection_url, unavailable
from code_factory.platform.errors import (
    DatabaseBusyError,
    MigrationsNotFoundError,
    SchemaMismatchError,
)

# A migration that cannot take its lock within 5 s fails instead of queueing behind a long query,
# which would also block every query that arrives after it. A statement running over 5 minutes is
# stuck or needs its own plan (an index build on a large table: see docs/architecture.md).
LOCK_TIMEOUT_MS = 5_000
STATEMENT_TIMEOUT_MS = 300_000

# SQLSTATE of "canceling statement due to lock timeout" and of a statement timeout.
_LOCK_NOT_AVAILABLE = "55P03"
_QUERY_CANCELED = "57014"
_UNKNOWN_REVISION = re.compile(r"Can't locate revision identified by '([^']+)'")

_ALEMBIC_INI = Path(__file__).with_name("alembic.ini")


def alembic_config() -> Config:
    """The Alembic configuration bundled with this build."""
    if not _ALEMBIC_INI.is_file():
        msg = f"{_ALEMBIC_INI} is missing; reinstall code-factory from a complete build"
        raise MigrationsNotFoundError(msg)
    return Config(str(_ALEMBIC_INI))


def create_migration_engine(settings: Settings) -> AsyncEngine:
    """The engine `alembic/env.py` uses: no pool, and the session timeouts set on connect."""
    return create_async_engine(
        connection_url(settings),
        poolclass=NullPool,
        connect_args={
            "server_settings": {
                "search_path": settings.db_schema,
                "lock_timeout": str(LOCK_TIMEOUT_MS),
                "statement_timeout": str(STATEMENT_TIMEOUT_MS),
            }
        },
    )


def upgrade(revision: str = "head") -> None:
    """Run `alembic upgrade`. Blocking: Alembic's env.py starts its own event loop."""
    settings = load_settings()
    config = alembic_config()
    try:
        command.upgrade(config, revision)
    except CommandError as error:
        unknown = _UNKNOWN_REVISION.search(str(error))
        if unknown is None:
            raise
        msg = (
            f"the database is at revision {unknown.group(1)}, which this build does not know; "
            "install the build that wrote the database, or restore it from a backup"
        )
        raise SchemaMismatchError(msg) from error
    except DBAPIError as error:
        busy = _busy(error)
        if busy is None:
            raise unavailable(settings, error) from error
        raise busy from error
    except DATABASE_ERRORS as error:
        raise unavailable(settings, error) from error


def _busy(error: DBAPIError) -> DatabaseBusyError | None:
    """The sentence for a lock or statement timeout; `None` for any other database error."""
    state = getattr(error.orig, "sqlstate", None)
    if state == _LOCK_NOT_AVAILABLE:
        return DatabaseBusyError(
            f"the migration could not take a lock within {LOCK_TIMEOUT_MS / 1000:g} s: another "
            "session holds a lock on the database (a running migration or a long query); "
            "retry when it has finished"
        )
    if state == _QUERY_CANCELED:
        return DatabaseBusyError(
            f"a migration statement ran longer than {STATEMENT_TIMEOUT_MS / 1000:g} s and was "
            "cancelled; see docs/architecture.md (Migrations) for long statements"
        )
    return None
