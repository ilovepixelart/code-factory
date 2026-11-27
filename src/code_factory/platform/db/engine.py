"""The async engine and session factory, plus the failures that mean "database unreachable"."""

import asyncio
from collections.abc import Callable

import asyncpg
from sqlalchemy import URL, text
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from code_factory.platform.config import DATABASE_URL_VARIABLE, Settings, parse_database_url
from code_factory.platform.errors import DatabaseUnavailableError, SettingsError
from code_factory.platform.keychain import SERVICE, database_password

# What a connection attempt or a statement raises when the server is down, refuses the login or
# does not answer in time.
DATABASE_ERRORS = (
    OSError,
    TimeoutError,
    SQLAlchemyError,
    asyncpg.PostgresError,
    asyncpg.InterfaceError,
)
_DETAIL_LIMIT = 200


def connection_url(
    settings: Settings, password_of: Callable[[str], str | None] = database_password
) -> URL:
    """The database URL every connection uses: a user without a password takes the keychain's."""
    url = parse_database_url(settings.database_url.get_secret_value())
    if url.password is not None or url.username in {None, ""}:
        return url
    password = password_of(str(url.username))
    if password is None:
        msg = (
            f"{DATABASE_URL_VARIABLE} names no password and the keychain holds none for "
            f"{url.username}: add it with security add-generic-password -a {url.username} "
            f"-s {SERVICE} -w"
        )
        raise SettingsError(msg)
    return url.set(password=password)


def create_engine(
    settings: Settings, password_of: Callable[[str], str | None] = database_password
) -> AsyncEngine:
    """Create the engine. Nothing connects until the first use.

    `pool_pre_ping` replaces a connection the server closed; `pool_timeout` makes a request wait
    at most that long for a free connection instead of queueing forever; the asyncpg `timeout`
    bounds opening a connection. A URL with a user and no password takes it from the keychain.
    """
    try:
        url = connection_url(settings, password_of)
        return create_async_engine(
            url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_s,
            pool_recycle=settings.db_pool_recycle_s,
            pool_pre_ping=True,
            connect_args={
                "timeout": settings.db_pool_timeout_s,
                "server_settings": {"search_path": settings.db_schema},
            },
        )
    except ArgumentError, ValueError, TypeError:
        # Their messages quote the URL, which holds the password.
        raise _engine_failed() from None


def _engine_failed() -> SettingsError:
    msg = (
        f"the database engine cannot be created from {DATABASE_URL_VARIABLE}; "
        "check the URL and the CODE_FACTORY_DB_* settings"
    )
    return SettingsError(msg)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Sessions that keep their objects readable after commit (no implicit lazy load in async)."""
    return async_sessionmaker(engine, expire_on_commit=False)


def unavailable(settings: Settings, error: BaseException) -> DatabaseUnavailableError:
    """One sentence for a failed connection: where, and the first line of why. No credentials."""
    detail = (str(error).splitlines() or [""])[0][:_DETAIL_LIMIT]
    reason = f"{type(error).__name__}: {detail}" if detail else type(error).__name__
    return DatabaseUnavailableError(
        f"the database at {settings.database_target} is not reachable ({reason})"
    )


async def ping(engine: AsyncEngine, timeout_s: float) -> None:
    """Run `select 1` within `timeout_s`; raises `TimeoutError` or a database error."""
    async with asyncio.timeout(timeout_s), engine.connect() as connection:
        await connection.execute(text("select 1"))
