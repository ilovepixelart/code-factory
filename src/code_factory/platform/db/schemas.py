"""Creating and dropping a whole schema: for the throwaway copies the browser tests serve."""

from sqlalchemy import text

from code_factory.platform.config import Settings
from code_factory.platform.db.engine import create_engine


async def create_schema(settings: Settings) -> None:
    """Create `settings.db_schema` if it does not exist."""
    await _execute(settings, f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"')


async def drop_schema(settings: Settings) -> None:
    """Drop `settings.db_schema` with everything in it."""
    await _execute(settings, f'DROP SCHEMA IF EXISTS "{settings.db_schema}" CASCADE')


async def _execute(settings: Settings, statement: str) -> None:
    # The name is validated by `Settings` as a plain lower-case identifier, so it is safe to quote.
    engine = create_engine(settings)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()
