import json
from pathlib import Path
from typing import Any

import pytest
from sample_world import World
from sessions_harness import Clock
from sessions_values import NOW, answer, golden
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.platform.text import Paging
from code_factory.sessions.models import StateFilter
from code_factory.sessions.service import SessionService

pytestmark = pytest.mark.usefixtures("sample")

TIMELINES = [
    item
    for item in golden("answers.json")
    if item["path"].endswith("/timeline") and item["status"] == 200
]


def mapping(found: object) -> dict[str, Any]:
    assert isinstance(found, dict)
    return found


def expected(world: World, body: Any) -> Any:  # noqa: ANN401  # a golden body of any shape
    """A golden body with its placeholders replaced by this test's folders."""
    shown = world.real(json.dumps(body)).replace("dcf92c3f", world.detached[:8])
    return json.loads(shown)


async def normalised(db: AsyncSession, found: Any) -> Any:  # noqa: ANN401
    """An answer with each `seq` counted from the first event of the sample, as the golden does."""
    first = (await db.execute(text("select min(seq) from session_events"))).scalar_one()
    for entry in found.get("entries", []):
        entry["seq"] -= first - 1
    return found


async def test_the_unpaged_list_is_the_list_the_previous_one_answered(
    sessions: SessionService, world: World
) -> None:
    await sessions.ingest_once()
    assert await sessions.list_sessions(None) == expected(world, answer("/api/sessions")["body"])


@pytest.mark.parametrize("item", TIMELINES, ids=[i["path"].split("/")[3] for i in TIMELINES])
async def test_a_sessions_timeline_is_the_one_the_previous_answer_gave(
    sessions: SessionService, db_session: AsyncSession, world: World, item: dict[str, Any]
) -> None:
    await sessions.ingest_once()
    session_id = item["path"].split("/")[3]
    found = await normalised(db_session, await sessions.timeline(session_id))
    assert found == expected(world, item["body"])


async def test_a_timeline_of_an_unknown_session_is_not_found_with_the_previous_sentence(
    sessions: SessionService,
) -> None:
    with pytest.raises(NotFoundError, match=r"^no such session$"):
        await sessions.timeline("nope")


async def test_the_timeline_window_keeps_the_last_entries_and_counts_earlier_prompts(
    sessions: SessionService,
) -> None:
    await sessions.ingest_once()
    found = mapping(await sessions.timeline("s-idle", last=3))
    assert [e["title"] for e in found["entries"]] == ["Bash", "Prompt", "Turn ended"]
    assert (found["total"], found["earlier_prompts"]) == (8, 1)


async def tool_seq(sessions: SessionService, session_id: str, tool: str) -> int:
    found = mapping(await sessions.timeline(session_id))
    return next(e["seq"] for e in found["entries"] if e["kind"] == "tool" and e["title"] == tool)


async def test_a_call_has_its_input_and_the_output_of_its_result(
    sessions: SessionService, world: World
) -> None:
    await sessions.ingest_once()
    seq = await tool_seq(sessions, "s-work", "Bash")
    assert await sessions.call("s-work", seq) == {
        "tool": "Bash",
        "input": {"command": "uv run pytest", "description": "tests"},
        "output": None,
    }
    assert world.root.is_dir()


async def test_a_call_that_is_still_running_has_no_output_and_a_failure_has_its_error(
    sessions: SessionService,
) -> None:
    await sessions.ingest_once()
    running = await sessions.call("s-work", await tool_seq(sessions, "s-work", "Read"))
    assert running == {"tool": "Read", "input": {"file_path": "/x/app.py"}, "output": None}
    failed = await sessions.call("s-idle", await tool_seq(sessions, "s-idle", "Grep"))
    assert failed == {"tool": "Grep", "input": {"pattern": "TODO"}, "output": None}


async def test_an_unknown_seq_or_another_sessions_call_is_not_found_with_the_previous_sentence(
    sessions: SessionService,
) -> None:
    await sessions.ingest_once()
    seq = await tool_seq(sessions, "s-work", "Bash")
    with pytest.raises(NotFoundError, match=r"^no call 9 in session s-1$"):
        await sessions.call("s-1", 9)
    with pytest.raises(NotFoundError, match=rf"^no call {seq} in session s-idle$"):
        await sessions.call("s-idle", seq)
    prompt = mapping(await sessions.timeline("s-work"))["entries"][1]
    with pytest.raises(NotFoundError):
        await sessions.call("s-work", prompt["seq"])


async def test_a_page_has_waiting_whole_the_rest_by_repository_and_the_ended_ones_counted(
    sessions: SessionService,
) -> None:
    await sessions.ingest_once()
    page = mapping(await sessions.list_sessions(Paging(1, 4)))
    assert [row["session_id"] for row in page["waiting"]] == ["s-block", "s-block2"]
    assert [row["session_id"] for row in page["rows"]] == ["zz", "s-sub", "s-work", "s-rest"]
    assert (page["total"], page["page"], page["size"], page["ended_hidden"]) == (6, 1, 4, 2)
    assert page["counts"] == {"waiting": 2, "working": 4, "idle": 2, "stale": 0}
    assert page["repositories"] == {"sample": 5, "unknown repository": 1}


async def test_ended_sessions_join_the_page_when_asked(sessions: SessionService) -> None:
    await sessions.ingest_once()
    page = mapping(await sessions.list_sessions(Paging(1, 100), ended=True))
    ids = [row["session_id"] for row in page["rows"]]
    assert "s-end" in ids
    assert "s-stale" in ids
    assert page["ended_hidden"] == 0


async def test_a_state_keeps_its_sessions_before_paging_and_the_counts_stay_whole(
    sessions: SessionService,
) -> None:
    await sessions.ingest_once()
    page = mapping(await sessions.list_sessions(Paging(1, 100), state=StateFilter.IDLE))
    assert [row["session_id"] for row in page["rows"]] == ["s-rest", "s-idle"]
    assert page["total"] == 2
    assert page["counts"]["working"] == 4


async def test_a_page_past_the_last_is_the_last(sessions: SessionService) -> None:
    await sessions.ingest_once()
    page = mapping(await sessions.list_sessions(Paging(99, 4)))
    assert page["page"] == 2
    assert [row["session_id"] for row in page["rows"]] == ["s-idle", ""]


async def test_the_unpaged_list_and_a_page_read_the_clock_at_the_moment_of_the_read(
    sessions: SessionService, clock: Clock
) -> None:
    await sessions.ingest_once()
    clock.seconds = NOW + 3600
    page = mapping(await sessions.list_sessions(Paging(1, 100)))
    ids = [row["session_id"] for row in page["rows"]]
    assert "s-work" not in ids
    assert [row["session_id"] for row in page["waiting"]] == ["s-block", "s-block2"]


async def test_the_board_sees_only_live_sessions_in_attention_order(
    sessions: SessionService,
) -> None:
    await sessions.ingest_once()
    live = await sessions.board_views()
    assert [view.session_id for view in live] == [
        "s-block", "s-block2", "zz", "", "s-sub", "s-work", "s-rest", "s-idle",
    ]  # fmt: skip
    assert all(view.state != "ended" for view in live)
    later = await sessions.board_views(NOW + 3600)
    assert [view.session_id for view in later] == ["s-block", "s-block2"]


async def test_a_running_subagent_at_work_is_reported_with_its_ticket_and_freshness(
    sessions: SessionService, state_dir: Path
) -> None:
    line = {
        "session_id": "s-sub",
        "hook_event_name": "PreToolUse",
        "agent_id": "a2",
        "tool_name": "Read",
        "tool_use_id": "r",
        "tool_input": {"file_path": "/r/.code-factory/worktrees/CF-7/a.py"},
        "_captured_at": NOW - 5,
    }
    with (state_dir / "spool" / "s-sub.jsonl").open("ab") as handle:
        handle.write(json.dumps(line).encode() + b"\n")
    await sessions.ingest_once()
    found = await sessions.subagents_at_work()
    assert [(w.ticket, w.session_id, w.agent_id, w.kind) for w in found] == [
        ("CF-7", "s-sub", "a2", "session")
    ]
    assert len(await sessions.subagents_at_work(fresh_only=True)) == 1
    assert await sessions.subagents_at_work(NOW + 1000, fresh_only=True) == []
    assert len(await sessions.subagents_at_work(NOW + 1000)) == 1


def test_a_state_query_other_than_the_four_is_refused() -> None:
    with pytest.raises(
        BadRequestError, match=r"^state must be one of waiting, working, idle, stale$"
    ):
        StateFilter.from_text("ended")


@pytest.mark.parametrize(
    ("seconds_after", "hidden", "listed"),
    [(3599.5, 4, True), (3600.0, 5, False)],
)
# By hand: s-stale, s-end, s-rest (630) and s-idle (150) are ended by then, s-work (970) the 5th.
async def test_a_working_session_leaves_the_page_exactly_3600_seconds_after_its_last_event(
    sessions: SessionService, clock: Clock, seconds_after: float, hidden: int, listed: bool
) -> None:
    await sessions.ingest_once()
    clock.seconds = 1790000970.0 + seconds_after  # s-work's last event
    page = mapping(await sessions.list_sessions(Paging(1, 100), state=None))
    ids = [row["session_id"] for row in page["rows"]]
    assert ("s-work" in ids) is listed
    assert page["ended_hidden"] == hidden


async def test_a_blocked_session_stays_on_the_page_whatever_the_time(
    sessions: SessionService, clock: Clock
) -> None:
    await sessions.ingest_once()
    clock.seconds = NOW + 86400
    page = mapping(await sessions.list_sessions(Paging(1, 100)))
    assert [row["session_id"] for row in page["waiting"]] == ["s-block", "s-block2"]


async def view_selects(
    connection: AsyncConnection, sessions: SessionService, paging: Paging, *, ended: bool
) -> list[str]:
    seen: list[str] = []

    def record(_c: object, _cur: object, statement: str, *_rest: object) -> None:
        flat = " ".join(statement.lower().split())
        if "from session_views" in flat and flat.startswith("select"):
            seen.append(flat)

    event.listen(connection.sync_connection, "before_cursor_execute", record)
    try:
        await sessions.list_sessions(paging, ended=ended)
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", record)
    return seen


async def test_a_page_reads_only_the_rows_not_ended_by_the_clock_unless_ended_ones_are_asked(
    sessions: SessionService, connection: AsyncConnection
) -> None:
    await sessions.ingest_once()
    live = await view_selects(connection, sessions, Paging(1, 10), ended=False)
    assert live
    assert all(" where " in statement for statement in live)
    every = await view_selects(connection, sessions, Paging(1, 10), ended=True)
    assert not any(" where " in statement for statement in every)


async def test_the_board_asked_for_an_earlier_moment_sees_the_sessions_live_then(
    sessions: SessionService, clock: Clock
) -> None:
    await sessions.ingest_once()
    clock.seconds = NOW + 7200  # everything that can end by the clock has, as of now
    assert [view.session_id for view in await sessions.board_views()] == ["s-block", "s-block2"]
    earlier = await sessions.board_views(NOW)
    assert [view.session_id for view in earlier][2:4] == ["zz", ""]
    assert len(earlier) == 8
    assert [w.agent_id for w in await sessions.subagents_at_work(NOW)] == []
