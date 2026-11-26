"""Advisory lock keys, one key space per schema.

A key is the 64-bit hash of `<schema>/<name>`, so two boards on separate schemas of one database
(and the test workers, each on its own schema) never wait on each other's locks. With no current
schema the schema part is empty rather than NULL: a NULL key takes no lock at all.
"""

from sqlalchemy import BigInteger, ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession


def lock_key(name: str) -> ColumnElement[int]:
    """The key of the advisory lock `name` in the current schema."""
    schema = func.coalesce(func.current_schema(), "")
    return func.hashtextextended(func.concat(schema, "/", name), 0, type_=BigInteger)


async def lock_until_commit(session: AsyncSession, name: str) -> None:
    """Wait for the lock `name` and hold it until the transaction ends."""
    await session.execute(select(func.pg_advisory_xact_lock(lock_key(name))))
