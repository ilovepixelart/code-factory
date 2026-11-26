"""The `schema_info` table, the engine and session, and the schema checks.

The only package that imports sqlalchemy and asyncpg.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from code_factory.platform.db.base import NAMING_CONVENTION, Base
from code_factory.platform.db.catalog import describe_tables
from code_factory.platform.db.engine import (
    DATABASE_ERRORS,
    connection_url,
    create_engine,
    create_session_factory,
    ping,
    unavailable,
)
from code_factory.platform.db.locks import lock_key, lock_until_commit
from code_factory.platform.db.schema import (
    DATA_FORMAT_VERSION,
    EXPECTED_REVISION,
    SchemaState,
    check_database,
    check_engine,
    read_schema_state,
    verify_schema,
)
from code_factory.platform.db.schemas import create_schema, drop_schema
from code_factory.platform.db.tables import SchemaInfo
from code_factory.platform.db.unit_of_work import NoDatabase, UnitOfWork

__all__ = [
    "DATABASE_ERRORS",
    "DATA_FORMAT_VERSION",
    "EXPECTED_REVISION",
    "NAMING_CONVENTION",
    "AsyncEngine",
    "AsyncSession",
    "Base",
    "NoDatabase",
    "SchemaInfo",
    "SchemaState",
    "UnitOfWork",
    "async_sessionmaker",
    "check_database",
    "check_engine",
    "connection_url",
    "create_engine",
    "create_schema",
    "create_session_factory",
    "describe_tables",
    "drop_schema",
    "lock_key",
    "lock_until_commit",
    "ping",
    "read_schema_state",
    "unavailable",
    "verify_schema",
]
