"""The permission hook as the service answers it: the run's wait, the owner's answer, the record."""

import asyncio
import logging
import time
from typing import Any

import pytest

from hooks_fakes import OWNER_ACTOR, Fakes, run_actor

REQUEST = {
    "session_id": "s-1",
    "hook_event_name": "PermissionRequest",
    "tool_name": "Bash",
    "tool_input": {"command": "npm test -- --watch"},
}
ALLOW_TEXT = (
    '{"hookSpecificOutput": {"hookEventName": "PermissionRequest", '
    '"decision": {"behavior": "allow"}}}'
)
OWNER_DENIED = {
    "hookSpecificOutput": {
        "hookEventName": "PermissionRequest",
        "decision": {
            "behavior": "deny",
            "message": "The owner denied this from the board.",
            "interrupt": True,
        },
    }
}
UNANSWERED = (
    "Nobody answered this permission request from the board in time; do it another way "
    "inside your worktree, or ask in the ticket's Open questions."
)


async def open_connection() -> bool:
    return True


async def test_a_request_with_no_ticket_on_the_actor_is_not_answered() -> None:
    fakes = Fakes()

    said = await fakes.service().permission(
        OWNER_ACTOR, REQUEST, sandboxed=False, alive=open_connection
    )
    coordinator = await fakes.service().permission(
        run_actor(ticket_id=None), REQUEST, sandboxed=False, alive=open_connection
    )

    assert (said, coordinator) == (None, None)
    assert fakes.permissions.requests == []


async def test_the_answer_of_the_permission_service_is_returned_as_hook_text() -> None:
    fakes = Fakes()

    said = await fakes.service().permission(
        run_actor(), REQUEST, sandboxed=True, alive=open_connection
    )

    assert said == ALLOW_TEXT
    ((run_id, payload, sandboxed, wait),) = fakes.permissions.requests
    assert (run_id, payload, sandboxed) == ("r-1", REQUEST, True)
    assert wait == 540


async def test_an_owner_denial_is_returned_with_its_interrupt() -> None:
    fakes = Fakes()
    fakes.permissions.answer = OWNER_DENIED

    said = await fakes.service().permission(
        run_actor(), REQUEST, sandboxed=False, alive=open_connection
    )

    assert said == (
        '{"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": '
        '{"behavior": "deny", "message": "The owner denied this from the board.", '
        '"interrupt": true}}}'
    )


async def test_every_answer_is_recorded_on_the_ticket_with_the_tool_the_decision_and_the_wait() -> (
    None
):
    fakes = Fakes()
    fakes.permissions.answer = OWNER_DENIED

    await fakes.service().permission(run_actor(), REQUEST, sandboxed=False, alive=open_connection)

    assert fakes.tickets.recorded == [
        ("CF-5", "permission", {"tool": "Bash", "decision": "deny", "waited": 0}, "board")
    ]


async def test_a_failure_to_record_is_logged_and_the_run_still_hears_the_answer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fakes = Fakes()
    fakes.tickets.fail_record = True

    with caplog.at_level(logging.WARNING):
        said = await fakes.service().permission(
            run_actor(), REQUEST, sandboxed=False, alive=open_connection
        )

    assert said == ALLOW_TEXT
    assert any("permission" in record.getMessage() for record in caplog.records)


async def test_a_request_nobody_answers_in_the_wait_is_told_so_and_withdrawn() -> None:
    fakes = Fakes()
    fakes.permissions.hold = True

    said = await fakes.service(wait_s=0.2, poll_s=0.05).permission(
        run_actor(), REQUEST, sandboxed=False, alive=open_connection
    )

    assert said == (
        '{"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": '
        f'{{"behavior": "deny", "message": "{UNANSWERED}"}}}}}}'
    )
    assert (fakes.permissions.cancelled, fakes.permissions.finished) == (1, 1)
    assert fakes.tickets.recorded[0][2]["decision"] == "deny"


async def test_a_hook_that_closed_withdraws_the_request_and_the_call_returns_nothing_at_once() -> (
    None
):
    fakes = Fakes()
    fakes.permissions.hold = True
    closed = False

    async def alive() -> bool:
        return not closed

    task = asyncio.create_task(
        fakes.service(poll_s=0.05).permission(run_actor(), REQUEST, sandboxed=False, alive=alive)
    )
    await asyncio.sleep(0.2)
    closed = True
    started = time.monotonic()

    said = await asyncio.wait_for(task, 3)

    assert said is None
    assert time.monotonic() - started < 1
    assert (fakes.permissions.cancelled, fakes.permissions.finished) == (1, 1)
    assert fakes.tickets.recorded == []


async def test_a_check_that_fails_does_not_end_the_wait() -> None:
    fakes = Fakes()
    fakes.permissions.hold = True
    calls = 0

    async def flaky() -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            msg = "the connection state is unreadable"
            raise RuntimeError(msg)
        return True

    task = asyncio.create_task(
        fakes.service(poll_s=0.05).permission(run_actor(), REQUEST, sandboxed=False, alive=flaky)
    )
    await asyncio.sleep(0.25)
    assert not task.done()
    fakes.permissions.release.set()

    assert await asyncio.wait_for(task, 3) == ALLOW_TEXT


async def test_cancelling_the_call_cancels_the_request_and_leaves_nothing_running() -> None:
    fakes = Fakes()
    fakes.permissions.hold = True
    task = asyncio.create_task(
        fakes.service(poll_s=0.05).permission(
            run_actor(), REQUEST, sandboxed=False, alive=open_connection
        )
    )
    await asyncio.sleep(0.1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert (fakes.permissions.cancelled, fakes.permissions.finished) == (1, 1)
    assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task()] == []


async def test_an_error_of_the_permission_service_reaches_the_caller() -> None:
    fakes = Fakes()
    fakes.permissions.error = LookupError("no such run")

    with pytest.raises(LookupError, match="no such run"):
        await fakes.service().permission(
            run_actor(), REQUEST, sandboxed=False, alive=open_connection
        )

    assert fakes.tickets.recorded == []


def edit(path: str) -> dict[str, Any]:
    return {"tool_name": "Edit", "tool_input": {"file_path": path}, "session_id": "s-1"}


async def test_an_edit_inside_the_runs_tree_is_allowed_for_codex_and_recorded_as_policy() -> None:
    fakes = Fakes()

    allowed = await fakes.service().codex_allows(run_actor(), edit("/t/a.py"), in_tree=True)

    assert allowed is True
    assert fakes.permissions.recorded == [
        ("r-1", "Edit", True, "policy", "an edit inside the run's tree")
    ]
    assert fakes.permissions.requests == []


async def test_a_standing_rule_of_the_requests_kind_allows_it_for_codex() -> None:
    fakes = Fakes()
    fakes.permissions.standing = ["Bash(npm test *)"]
    payload = {"tool_name": "Bash", "tool_input": {"command": "npm test"}}

    allowed = await fakes.service().codex_allows(run_actor(), payload, in_tree=False)

    assert allowed is True
    assert fakes.permissions.recorded == [
        ("r-1", "Bash", True, "owner", "a standing rule of the owner")
    ]
    assert fakes.permissions.requests == []


async def test_a_request_with_no_rule_goes_the_permission_path_and_only_an_allow_counts() -> None:
    fakes = Fakes()
    allowed = await fakes.service().codex_allows(run_actor(), REQUEST, in_tree=False)
    fakes.permissions.answer = OWNER_DENIED
    denied = await fakes.service().codex_allows(run_actor(), REQUEST, in_tree=False)

    assert (allowed, denied) == (True, False)
    assert len(fakes.permissions.requests) == 2
    assert fakes.permissions.requests[0][2] is False


async def test_codex_is_denied_with_no_ticket_and_when_nobody_answers() -> None:
    fakes = Fakes()
    nobody = await fakes.service().codex_allows(OWNER_ACTOR, REQUEST, in_tree=True)
    fakes.permissions.hold = True
    silent = await fakes.service(wait_s=0.1, poll_s=0.05).codex_allows(
        run_actor(), REQUEST, in_tree=False
    )

    assert (nobody, silent) == (False, False)
