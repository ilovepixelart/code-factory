"""Advisory lock keys, one key space per schema.

A key is the 64-bit hash of `<schema>/<name>`, so two boards on separate schemas of one database
(and the test workers, each on its own schema) never wait on each other's locks. With no current
schema the schema part is empty rather than NULL: a NULL key takes no lock at all.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import BigInteger, ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


def lock_key(name: str) -> ColumnElement[int]:
    """The key of the advisory lock `name` in the current schema."""
    schema = func.coalesce(func.current_schema(), "")
    return func.hashtextextended(func.concat(schema, "/", name), 0, type_=BigInteger)


async def lock_until_commit(session: AsyncSession, name: str) -> None:
    """Wait for the lock `name` and hold it until the transaction ends."""
    await session.execute(select(func.pg_advisory_xact_lock(lock_key(name))))


@asynccontextmanager
async def try_session_lock(engine: AsyncEngine, name: str) -> AsyncGenerator[bool]:
    """Try a lock held by a dedicated database session until the block exits."""
    async with engine.connect() as connection:
        # Closing the connection must end the session even if cancellation interrupted acquisition.
        # A long-running command must also leave the application's pool available for ordinary work.
        (await connection.get_raw_connection()).detach()
        acquired = await connection.scalar(select(func.pg_try_advisory_lock(lock_key(name))))
        await connection.commit()
        yield bool(acquired)
