"""The releases tables as the commands spec names them (Tables), read from the live database."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_the_version_is_unique_per_repository_under_the_spec_name(
    db_session: AsyncSession,
) -> None:
    found = await db_session.scalars(
        text(
            "select conname from pg_constraint "
            "where conrelid = 'releases'::regclass and contype = 'u'"
        )
    )
    assert list(found) == ["uq_releases_repository_version"]
