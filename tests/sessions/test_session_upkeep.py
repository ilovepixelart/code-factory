import asyncio
import json
import os
import shlex
import stat
from datetime import datetime
from pathlib import Path

import pytest
from sessions_harness import Clock, Committed
from sessions_values import NOW
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.errors import BadRequestError, UnavailableError
from code_factory.sessions.models import Failure, PruneReport, Recurrence, ReportedTokens
from code_factory.sessions.repository.ledger import LOCK_KEY
from code_factory.sessions.rules import capture
from code_factory.sessions.service import SessionService


def request(input_tokens: object, output_tokens: object) -> dict[str, object]:
    return {
        "body": {"stringValue": "claude_code.api_request"},
        "attributes": [
            {"key": "input_tokens", "value": {"intValue": input_tokens}},
            {"key": "output_tokens", "value": {"intValue": output_tokens}},
        ],
    }


def export(*records: dict[str, object]) -> dict[str, object]:
    return {"resourceLogs": [{"scopeLogs": [{"logRecords": list(records)}]}]}


async def test_the_requests_of_a_run_add_up_to_the_tokens_it_reported(
    sessions: SessionService,
) -> None:
    taken = await sessions.record_run_requests("run-1", export(request(285, "89"), request(1, 2)))
    await sessions.record_run_requests("run-1", export(request(10, 20)))
    await sessions.record_run_requests("run-2", export(request(7, 8)))
    assert taken == 2
    assert await sessions.run_reported_tokens(["run-1", "run-2", "run-3"]) == {
        "run-1": ReportedTokens(296, 111),
        "run-2": ReportedTokens(7, 8),
    }
    assert await sessions.run_reported_tokens([]) == {}


async def test_an_export_with_no_request_event_inserts_nothing(
    sessions: SessionService, db_session: AsyncSession
) -> None:
    other: dict[str, object] = {
        "body": {"stringValue": "claude_code.tool_result"},
        "attributes": [],
    }
    assert await sessions.record_run_requests("run-1", export(other)) == 0
    assert await sessions.record_run_requests("run-1", {}) == 0
    assert (
        await db_session.execute(text("select count(*) from session_run_requests"))
    ).scalar_one() == 0


@pytest.mark.parametrize("body", [[], "text", 5, None])
async def test_an_export_that_is_not_an_object_is_refused_with_a_sentence(
    sessions: SessionService, body: object
) -> None:
    with pytest.raises(BadRequestError, match=r"^the telemetry export must be a JSON object$"):
        await sessions.record_run_requests("run-1", body)


async def test_the_tokens_of_a_run_saturate_at_the_largest_bigint(
    sessions: SessionService, db_session: AsyncSession
) -> None:
    biggest = 2**63 - 1
    await db_session.execute(
        text(
            "insert into session_run_requests (run_id, input_tokens, output_tokens) "
            "values ('r', :big, 1), ('r', :big, 2)"
        ),
        {"big": biggest},
    )
    assert await sessions.run_reported_tokens(["r"]) == {"r": ReportedTokens(biggest, 3)}


async def test_forgetting_a_run_deletes_only_its_requests(sessions: SessionService) -> None:
    await sessions.record_run_requests("run-1", export(request(1, 1), request(2, 2)))
    await sessions.record_run_requests("run-2", export(request(3, 3)))
    assert await sessions.forget_run("run-1") == 2
    assert await sessions.forget_run("run-1") == 0
    assert list(await sessions.run_reported_tokens(["run-1", "run-2"])) == ["run-2"]


def names_in(folder: Path) -> list[str]:
    return [p.name for p in folder.iterdir()]


async def test_the_published_redaction_is_owner_only_whole_and_longest_first(
    sessions: SessionService, state_dir: Path
) -> None:
    await sessions.publish_redaction(
        [("short", "[a]"), ("a much longer context", "[b]")], ["agent@3"]
    )
    path = state_dir / "redaction.json"
    assert json.loads(path.read_text()) == {
        "references": ["agent@3"],
        "patterns": [["a much longer context", "[b]"], ["short", "[a]"]],
    }
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert names_in(state_dir) == ["redaction.json"]


async def test_a_context_holding_another_is_listed_before_it_whatever_the_alphabet(
    sessions: SessionService, state_dir: Path
) -> None:
    await sessions.publish_redaction([("zz", "[a]"), ("zz b", "[b]")], [])
    found = json.loads((state_dir / "redaction.json").read_text())
    assert found["patterns"] == [["zz b", "[b]"], ["zz", "[a]"]]


async def test_the_capture_hook_command_keeps_an_owner_context_out_of_the_spool(
    sessions: SessionService, state_dir: Path
) -> None:
    await sessions.publish_redaction([("the owner secret", "[ctx]")], ["agent@3"])
    hook = sessions.capture_hook()
    assert hook.asynchronous is True
    process = await asyncio.create_subprocess_exec(
        *shlex.split(hook.command),
        stdin=asyncio.subprocess.PIPE,
        env={"CODE_FACTORY_STATE_DIR": "/elsewhere", "CODE_FACTORY_CONTEXT": "agent@3"},
    )
    async with asyncio.timeout(20):
        await process.communicate(b'{"session_id": "s", "prompt": "Go. the owner secret"}')
    assert process.returncode == 0
    line = json.loads((state_dir / "spool" / "s.jsonl").read_text())
    assert line["prompt"] == "Go. [ctx]"


def test_the_capture_hook_is_installed_asynchronously_on_the_events_the_ledger_reads(
    sessions: SessionService, state_dir: Path
) -> None:
    hook = sessions.capture_hook()
    command = shlex.split(hook.command)
    # The state folder travels in the command: an agent need not inherit the board's variable.
    assert command[:2] == ["/usr/bin/env", f"CODE_FACTORY_STATE_DIR={state_dir}"]
    assert command[3:5] == ["-I", "-S"]
    assert Path(command[5]).name == "capture.py"
    assert Path(command[2]).is_absolute()
    assert hook.events == (
        "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
        "PostToolUseFailure", "PermissionRequest", "Notification", "SubagentStart",
        "SubagentStop", "Stop",
    )  # fmt: skip


def spool_line(session: str, **payload: object) -> bytes:
    return json.dumps({"session_id": session, "_captured_at": NOW - 10, **payload}).encode() + b"\n"


def gate_output(
    session: str, *steps: tuple[str, int], tool: str = "Bash", key: str = "stdout"
) -> bytes:
    lines = "\n".join(f"gate: {step} failed (exit {code})" for step, code in steps)
    return spool_line(
        session,
        hook_event_name="PostToolUse",
        tool_name=tool,
        tool_response={key: "running\n" + lines + "\n"},
    )


async def recurrences(sessions: SessionService, state_dir: Path, *lines: bytes) -> list[Recurrence]:
    spool = state_dir / "spool"
    spool.mkdir(parents=True, exist_ok=True)
    (spool / "all.jsonl").write_bytes(b"".join(lines))
    await sessions.ingest_once()
    return await sessions.recurring_failures(datetime.fromtimestamp(NOW - 100, tz=Clock()().tzinfo))


async def test_the_same_gate_failure_in_three_sessions_is_one_recurrence(
    sessions: SessionService, state_dir: Path
) -> None:
    found = await recurrences(
        sessions,
        state_dir,
        gate_output("c", ("pytest", 1)),
        gate_output("a", ("pytest", 1)),
        gate_output("b", ("pytest", 1), ("ruff", 1)),
    )
    assert found == [Recurrence(Failure("pytest", 1), ["a", "b", "c"])]


async def test_two_sessions_or_one_session_three_times_are_no_recurrence(
    sessions: SessionService, state_dir: Path
) -> None:
    two = await recurrences(
        sessions, state_dir, gate_output("a", ("pytest", 1)), gate_output("b", ("pytest", 1))
    )
    assert two == []
    assert await sessions.recurring_failures(datetime.fromtimestamp(0, tz=Clock()().tzinfo)) == []
    spool = state_dir / "spool" / "all.jsonl"
    spool.write_bytes(spool.read_bytes() + gate_output("a", ("pytest", 1)) * 2)
    await sessions.ingest_once()
    assert await sessions.recurring_failures(datetime.fromtimestamp(0, tz=Clock()().tzinfo)) == []


async def test_stderr_and_a_failed_tools_error_count_and_other_tools_and_old_output_do_not(
    sessions: SessionService, state_dir: Path
) -> None:
    failure = spool_line(
        "c",
        hook_event_name="PostToolUseFailure",
        tool_name="Bash",
        error="gate: pytest failed (exit 1)",
    )
    found = await recurrences(
        sessions,
        state_dir,
        gate_output("a", ("pytest", 1), key="stderr"),
        gate_output("b", ("pytest", 1)),
        failure,
        gate_output("d", ("pytest", 1), tool="Read"),
    )
    assert found == [Recurrence(Failure("pytest", 1), ["a", "b", "c"])]
    later = datetime.fromtimestamp(NOW, tz=Clock()().tzinfo)
    assert await sessions.recurring_failures(later) == []


def age(path: Path, days: float) -> None:
    moment = NOW - days * 86400
    os.utime(path, (moment, moment))


COUNTS = {
    name: f"select count(*) from {name}"  # noqa: S608  # a fixed table name of this module
    for name in ("session_events", "session_rejects", "session_run_requests")
}


async def count(db: AsyncSession, table: str) -> int:
    found = (await db.execute(text(COUNTS[table]))).scalar_one()
    assert isinstance(found, int)
    return found


async def two_old_and_one_new(sessions: SessionService, state_dir: Path) -> tuple[Path, Path, Path]:
    spool = state_dir / "spool"
    spool.mkdir(parents=True)
    old = spool / "old.jsonl"
    old.write_bytes(spool_line("old", hook_event_name="Stop") + b"not json\n")
    older = spool / "older.jsonl"
    older.write_bytes(spool_line("older", hook_event_name="Stop"))
    new = spool / "new.jsonl"
    new.write_bytes(spool_line("new", hook_event_name="Stop"))
    await sessions.ingest_once()
    age(old, 40)
    age(older, 100)
    age(new, 1)
    return old, older, new


async def test_a_dry_run_lists_what_pruning_would_remove_and_removes_nothing(
    sessions: SessionService, state_dir: Path, db_session: AsyncSession
) -> None:
    old, older, _ = await two_old_and_one_new(sessions, state_dir)
    report = await sessions.prune_spools(30, apply=False)
    assert report == PruneReport(2, 2, 1, old.stat().st_size + older.stat().st_size)
    assert old.exists()
    assert older.exists()
    assert await count(db_session, "session_events") == 3


async def test_applying_a_prune_removes_old_files_rows_progress_and_orphan_views(
    sessions: SessionService, state_dir: Path, db_session: AsyncSession
) -> None:
    old, older, new = await two_old_and_one_new(sessions, state_dir)
    await db_session.execute(
        text(
            "insert into session_run_requests (run_id, input_tokens, output_tokens, reported_at) "
            "values ('r', 1, 1, to_timestamp(0)), ('r', 2, 2, now())"
        )
    )
    report = await sessions.prune_spools(30, apply=True)
    assert (report.spools, report.events, report.rejects) == (2, 2, 1)
    assert [old.exists(), older.exists(), new.exists()] == [False, False, True]
    spools = (await db_session.execute(text("select distinct spool from session_events"))).scalars()
    assert list(spools) == ["new.jsonl"]
    assert await count(db_session, "session_rejects") == 0
    progress = (
        await db_session.execute(text("select spool from session_spool_progress"))
    ).scalars()
    assert list(progress) == ["new.jsonl"]
    views = (await db_session.execute(text("select session_id from session_views"))).scalars()
    assert list(views) == ["new"]
    assert await count(db_session, "session_run_requests") == 1


async def test_a_spool_that_cannot_be_removed_keeps_its_progress_so_it_is_not_taken_in_again(
    sessions: SessionService, state_dir: Path, db_session: AsyncSession
) -> None:
    if os.geteuid() == 0:
        pytest.skip("root removes anything")
    old, _, _ = await two_old_and_one_new(sessions, state_dir)
    folder = state_dir / "spool"
    folder.chmod(0o500)
    try:
        await sessions.prune_spools(30, apply=True)
        assert old.exists()
        taken = await sessions.ingest_once()
    finally:
        folder.chmod(0o700)
    assert taken.lines == 0
    progress = (
        await db_session.execute(text("select spool from session_spool_progress"))
    ).scalars()
    assert "old.jsonl" in list(progress)
    assert await count(db_session, "session_events") == 1


async def insert_old_and_new_run_requests(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            "insert into session_run_requests (run_id, input_tokens, output_tokens, reported_at) "
            "values ('r', 1, 1, to_timestamp(0)), ('r', 2, 2, now())"
        )
    )


async def test_old_run_requests_are_pruned_when_no_spool_is_old(
    sessions: SessionService, db_session: AsyncSession
) -> None:
    await insert_old_and_new_run_requests(db_session)
    report = await sessions.prune_spools(30, apply=True)
    assert report == PruneReport(run_requests=1)
    assert await count(db_session, "session_run_requests") == 1


async def test_a_dry_run_counts_old_run_requests_and_keeps_them(
    sessions: SessionService, db_session: AsyncSession
) -> None:
    await insert_old_and_new_run_requests(db_session)
    assert await sessions.prune_spools(30, apply=False) == PruneReport(run_requests=1)
    assert await count(db_session, "session_run_requests") == 2


async def test_nothing_old_means_an_empty_report(sessions: SessionService, state_dir: Path) -> None:
    await two_old_and_one_new(sessions, state_dir)
    assert await sessions.prune_spools(365, apply=True) == PruneReport()


def captured_output(session: str, *steps: tuple[str, int], key: str = "stdout") -> bytes:
    """A Bash result as the real hook records it: output too long to keep is trimmed."""
    lines = "".join(f"gate: {step} failed (exit {code})\n" for step, code in steps)
    payload = {
        "session_id": session,
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_response": {key: "noise\n" * 600 + lines},
    }
    made = capture.record(json.dumps(payload).encode(), NOW - 10)
    assert isinstance(made, capture.Record)
    return str(made.line).encode()


async def test_gate_failures_in_output_too_long_to_keep_still_count(
    sessions: SessionService, state_dir: Path
) -> None:
    found = await recurrences(
        sessions,
        state_dir,
        captured_output("a", ("pytest", 1)),
        captured_output("b", ("pytest", 1), ("ruff", 2)),
        captured_output("c", ("pytest", 1), key="stderr"),
    )
    assert found == [Recurrence(Failure("pytest", 1), ["a", "b", "c"])]


async def test_a_prune_that_cannot_take_the_ingest_lock_removes_nothing(
    committed: Committed, tmp_path: Path
) -> None:
    state_dir = tmp_path / "state"
    spool = state_dir / "spool"
    spool.mkdir(parents=True)
    old = spool / "old.jsonl"
    old.write_bytes(spool_line("old", hook_event_name="Stop"))
    service = committed.make(state_dir, clock=Clock(), lock_wait_ms=200)
    await service.ingest_once(wait=True)
    age(old, 40)
    async with committed.admin.connect() as holder:
        await holder.execute(text(f"select pg_advisory_lock({LOCK_KEY})"))
        try:
            with pytest.raises(UnavailableError, match="another ingest holds the lock"):
                await service.prune_spools(30, apply=True)
            with pytest.raises(UnavailableError, match="another ingest holds the lock"):
                await service.rebuild_views()
        finally:
            await holder.execute(text(f"select pg_advisory_unlock({LOCK_KEY})"))
    assert old.exists()
    async with committed.admin.connect() as connection:
        found = await connection.scalar(text("select count(*) from session_events"))
    assert found == 1
