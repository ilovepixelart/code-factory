"""The `column_limits` table: one limit per board column, refused by named checks otherwise."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

AT = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)
INSERT = "insert into column_limits (stage, max_open, updated_at) values (:stage, :max, :at)"


async def put(session: AsyncSession, stage: str, limit: int) -> None:
    async with session.begin_nested():
        await session.execute(text(INSERT), {"stage": stage, "max": limit, "at": AT})


async def test_a_limit_is_kept_per_column_and_a_second_one_for_it_is_refused(
    db_session: AsyncSession,
) -> None:
    await put(db_session, "spec", 2)
    await put(db_session, "build", 3)

    with pytest.raises(IntegrityError, match="pk_column_limits"):
        await put(db_session, "spec", 5)


async def test_a_name_that_is_no_column_cannot_hold_a_limit(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_column_limits_known_stage"):
        await put(db_session, "bogus", 1)
    with pytest.raises(IntegrityError, match="ck_column_limits_known_stage"):
        await put(db_session, "released", 1)


@pytest.mark.parametrize("limit", [0, -1])
async def test_a_limit_must_be_positive(db_session: AsyncSession, limit: int) -> None:
    with pytest.raises(IntegrityError, match="ck_column_limits_max_open_positive"):
        await put(db_session, "review", limit)
    await put(db_session, "review", 1)
