import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.sessions.service import SessionService
from sample_world import World
from sessions_values import golden


async def event_rows(db: AsyncSession) -> list[tuple[Any, ...]]:
    found = await db.execute(
        text(
            "select seq, session_id, agent_id, event, extract(epoch from captured_at)::float8, "
            "spool, spool_offset, payload::text from session_events order by seq"
        )
    )
    return [tuple(row) for row in found]


def line_number(spool: Path, offset: int) -> int:
    return spool.read_bytes()[:offset].count(b"\n")


async def test_the_sample_spool_ingested_is_the_ledger_the_previous_one_held(
    sessions: SessionService, db_session: AsyncSession, sample: World, state_dir: Path
) -> None:
    expected = golden("ledger.golden.json")
    taken = await sessions.ingest_once()
    assert (taken.lines, taken.rejects) == (45, 2)
    rows = await event_rows(db_session)
    first = rows[0][0]
    got = [
        [
            seq - first + 1,
            session_id,
            agent_id,
            event,
            at,
            spool,
            line_number(state_dir / "spool" / spool, offset),
            json.loads(sample.placeholders(payload)),
        ]
        for seq, session_id, agent_id, event, at, spool, offset, payload in rows
    ]
    want = [[*row[:7], json.loads(row[7])] for row in expected["events"]]
    assert got == want
    # Key order is part of the stream's answer: the payload text keeps it.
    assert [json.dumps(row[7]) for row in got] == [json.dumps(row[7]) for row in want]


@pytest.mark.usefixtures("sample")
async def test_the_sample_spools_rejects_and_progress_are_the_previous_ones(
    sessions: SessionService, db_session: AsyncSession, state_dir: Path
) -> None:
    expected = golden("ledger.golden.json")
    await sessions.ingest_once()
    rejects = await db_session.execute(
        text("select spool, spool_offset, reason, head from session_rejects order by seq")
    )
    got = [
        [spool, line_number(state_dir / "spool" / spool, offset), reason.split(":")[0], head]
        for spool, offset, reason, head in rejects
    ]
    want = [[r[1], r[2], r[3].split(":")[0], r[4]] for r in expected["rejects"]]
    assert got == want
    progress = await db_session.execute(
        text("select spool, byte_offset from session_spool_progress")
    )
    assert (
        sorted(
            [spool, line_number(state_dir / "spool" / spool, offset)] for spool, offset in progress
        )
        == expected["progress"]
    )


@pytest.mark.usefixtures("sample")
async def test_ingesting_again_takes_nothing(sessions: SessionService) -> None:
    await sessions.ingest_once()
    again = await sessions.ingest_once()
    assert (again.lines, again.rejects, again.sessions) == (0, 0, 0)
