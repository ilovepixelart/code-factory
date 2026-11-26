"""What the sessions tables refuse by themselves, whatever code writes to them."""

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

INSERT_EVENT = (
    "insert into session_events (session_id, event, captured_at, spool, spool_offset, payload) "
    "values ('s', 'Stop', now(), 'a.jsonl', 0, '{}')"
)


async def test_a_line_of_a_spool_is_one_event_whatever_inserts_it(db_session: AsyncSession) -> None:
    await db_session.execute(text(INSERT_EVENT))
    with pytest.raises(DBAPIError, match="uq_session_events_spool_spool_offset"):
        await db_session.execute(text(INSERT_EVENT))


async def test_a_seq_comes_only_from_the_sequence(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError, match="cannot insert a non-DEFAULT value into column"):
        await db_session.execute(
            text(
                "insert into session_events (seq, session_id, event, captured_at, spool, "
                "spool_offset, payload) values (7, 's', 'Stop', now(), 'a.jsonl', 0, '{}')"
            )
        )


async def test_a_negative_progress_or_token_count_is_refused(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError, match="ck_session_spool_progress_byte_offset"):
        await db_session.execute(
            text("insert into session_spool_progress (spool, byte_offset) values ('a', -1)")
        )


async def test_a_negative_token_count_is_refused(db_session: AsyncSession) -> None:
    with pytest.raises(DBAPIError, match="ck_session_run_requests_input_tokens"):
        await db_session.execute(
            text(
                "insert into session_run_requests (run_id, input_tokens, output_tokens) "
                "values ('r', -1, 0)"
            )
        )


async def test_a_payload_keeps_the_order_of_its_keys_and_the_view_is_jsonb(
    db_session: AsyncSession,
) -> None:
    await db_session.execute(
        text(
            "insert into session_events "
            "(session_id, event, captured_at, spool, spool_offset, payload) "
            "values ('s', 'Stop', now(), 'a.jsonl', 0, :payload)"
        ),
        {"payload": json.dumps({"b": 1, "a": 2, "c": {"z": 1, "y": 2}})},
    )
    stored = (
        await db_session.execute(text("select payload::text from session_events"))
    ).scalar_one()
    assert stored == '{"b": 1, "a": 2, "c": {"z": 1, "y": 2}}'
    kinds = dict(
        (
            await db_session.execute(
                text(
                    "select column_name, data_type from information_schema.columns "
                    "where table_schema = current_schema() "
                    "and ((table_name = 'session_events' and column_name = 'payload') "
                    "or (table_name = 'session_views' and column_name = 'view'))"
                )
            )
        ).all()
    )
    assert kinds == {"payload": "json", "view": "jsonb"}


async def test_the_session_views_are_indexed_for_the_two_reads_of_the_page(
    db_session: AsyncSession,
) -> None:
    found = await db_session.scalars(
        text(
            "select indexname from pg_indexes "
            "where schemaname = current_schema() and tablename = 'session_views' "
            "order by indexname"
        )
    )
    assert list(found) == [
        "ix_session_views_last_event_at",
        "ix_session_views_state_last_event_at",
        "pk_session_views",
    ]
