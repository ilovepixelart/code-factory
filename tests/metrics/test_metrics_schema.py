"""The metrics tables as the module spec names them, read from the live database."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

INSERT = (
    "insert into metrics_merges (repository, commit, head, branch, merged_at, started_at, "
    "refreshed_at, {extra}) values ('r', 'c', 'h', 'b', now(), now(), now(), {values})"
)


async def names(session: AsyncSession, query: str) -> list[str]:
    return sorted(await session.scalars(text(query)))


async def test_the_merges_table_has_its_key_check_constraints_and_index_under_the_convention(
    db_session: AsyncSession,
) -> None:
    assert await names(
        db_session,
        "select conname from pg_constraint where conrelid = 'metrics_merges'::regclass "
        "and contype in ('c', 'p', 'u', 'f')",
    ) == [
        "ck_metrics_merges_autonomy",
        "ck_metrics_merges_checks",
        "pk_metrics_merges",
    ]
    assert await names(
        db_session,
        "select indexname from pg_indexes where tablename = 'metrics_merges' "
        "and schemaname = current_schema()",
    ) == ["ix_metrics_merges_merged_at", "pk_metrics_merges"]


async def test_the_merges_key_is_repository_then_commit(db_session: AsyncSession) -> None:
    found = await db_session.scalars(
        text(
            "select a.attname from pg_index i join pg_attribute a on a.attrelid = i.indrelid "
            "and a.attnum = any(i.indkey) where i.indrelid = 'metrics_merges'::regclass "
            "and i.indisprimary order by array_position(i.indkey::int[], a.attnum::int)"
        )
    )
    assert list(found) == ["repository", "commit"]


async def test_a_row_takes_the_defaults_unknown_none_and_not_reverted(
    db_session: AsyncSession,
) -> None:
    await db_session.execute(text(INSERT.format(extra="pull", values="7")))
    row = (
        await db_session.execute(
            text("select reverted, autonomy, checks, pull from metrics_merges")
        )
    ).one()
    assert tuple(row) == (False, "unknown", "none", 7)


@pytest.mark.parametrize(
    ("column", "word"), [("autonomy", "sometimes"), ("checks", "maybe"), ("autonomy", "")]
)
async def test_a_word_outside_the_classes_is_refused_by_the_table(
    db_session: AsyncSession, column: str, word: str
) -> None:
    with pytest.raises(IntegrityError, match=f"ck_metrics_merges_{column}"):
        async with db_session.begin_nested():
            await db_session.execute(text(INSERT.format(extra=column, values=f"'{word}'")))


@pytest.mark.parametrize(("column", "word"), [("autonomy", "assisted"), ("checks", "failed")])
async def test_a_word_of_the_classes_is_accepted_by_the_table(
    db_session: AsyncSession, column: str, word: str
) -> None:
    await db_session.execute(text(INSERT.format(extra=column, values=f"'{word}'")))


async def test_a_branch_cut_may_have_no_time_and_a_repository_branch_pair_is_one_row(
    db_session: AsyncSession,
) -> None:
    insert = text(
        "insert into metrics_branch_cuts (repository, branch, refreshed_at) "
        "values ('r', 'ticket/cf-1', now())"
    )
    await db_session.execute(insert)
    with pytest.raises(IntegrityError, match="pk_metrics_branch_cuts"):
        async with db_session.begin_nested():
            await db_session.execute(insert)
