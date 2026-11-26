"""The tell, permission and recall hooks: thin clients of the board over loopback HTTP."""

import json
import socket
import threading
import time
from pathlib import Path

import pytest

from hooks_support import FakeBoard, Reply, board_env, run_hook

TOKEN = "cfr_" + "t" * 43
TOOL_USED = json.dumps({"session_id": "s-1", "hook_event_name": "PostToolUse", "tool_name": "Bash"})
NEWS = '{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "hello"}}'
MARKS = {"through_post": 4, "through_answer": 2, "message_ids": [3]}


def tell_reply() -> Reply:
    return Reply(200, json.dumps({"output": NEWS, "confirm": MARKS}).encode())


def test_news_is_printed_then_confirmed_with_the_marks_the_board_gave(tmp_path: Path) -> None:
    replies = {"/api/hooks/tell": tell_reply(), "/api/hooks/tell/confirm": Reply(204)}
    with FakeBoard(replies) as board:
        ran = run_hook("tell", TOOL_USED, cwd=tmp_path, env=board_env(board.url))

    assert (ran.code, ran.out, ran.err) == (0, NEWS, "")
    asked, confirmed = board.requests
    assert asked.path == "/api/hooks/tell"
    assert asked.body == {"session_id": "s-1", "hook_event_name": "PostToolUse"}
    assert asked.authorization == f"Bearer {TOKEN}"
    assert asked.content_type == "application/json"
    assert confirmed.path == "/api/hooks/tell/confirm"
    assert confirmed.body == {"session_id": "s-1", "confirm": MARKS}


def test_nothing_to_say_prints_nothing_and_confirms_nothing(tmp_path: Path) -> None:
    with FakeBoard({"/api/hooks/tell": Reply(204)}) as board:
        ran = run_hook("tell", TOOL_USED, cwd=tmp_path, env=board_env(board.url))

    assert (ran.code, ran.out, ran.err) == (0, "", "")
    assert [seen.path for seen in board.requests] == ["/api/hooks/tell"]


def test_no_token_means_no_call(tmp_path: Path) -> None:
    with FakeBoard({"/api/hooks/tell": tell_reply()}) as board:
        ran = run_hook("tell", TOOL_USED, cwd=tmp_path, env={"CODE_FACTORY_URL": board.url})

    assert (ran.code, ran.out) == (0, "")
    assert board.requests == []


def test_a_board_that_is_not_on_a_loopback_address_is_not_called(tmp_path: Path) -> None:
    with FakeBoard({"/api/hooks/tell": tell_reply()}) as board:
        port = board.url.rsplit(":", 1)[1]
        ran = run_hook("tell", TOOL_USED, cwd=tmp_path, env=board_env(f"http://0.0.0.0:{port}"))

    assert (ran.code, ran.out) == (0, "")
    assert board.requests == []


def test_a_board_that_is_down_prints_nothing_and_exits_zero_quickly(tmp_path: Path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    started = time.monotonic()

    ran = run_hook("tell", TOOL_USED, cwd=tmp_path, env=board_env(f"http://127.0.0.1:{port}"))

    assert (ran.code, ran.out, ran.err) == (0, "", "")
    assert time.monotonic() - started < 3


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_a_refusal_or_error_from_the_board_prints_nothing(tmp_path: Path, status: int) -> None:
    with FakeBoard({"/api/hooks/tell": Reply(status, b'{"error": "no"}')}) as board:
        ran = run_hook("tell", TOOL_USED, cwd=tmp_path, env=board_env(board.url))

    assert (ran.code, ran.out, ran.err) == (0, "", "")


@pytest.mark.parametrize("status", [201, 400, 500])
def test_only_a_200_answer_is_used_even_if_its_body_has_an_output(
    tmp_path: Path, status: int
) -> None:
    with FakeBoard({"/api/hooks/tell": Reply(status, tell_reply().body)}) as board:
        ran = run_hook("tell", TOOL_USED, cwd=tmp_path, env=board_env(board.url))

    assert (ran.code, ran.out, ran.err) == (0, "", "")


@pytest.mark.parametrize("body", [b"", b"not json", b"[1]", b'{"output": 5}', b'{"other": 1}'])
def test_an_answer_that_is_not_the_expected_shape_prints_nothing(
    tmp_path: Path, body: bytes
) -> None:
    with FakeBoard({"/api/hooks/tell": Reply(200, body)}) as board:
        ran = run_hook("tell", TOOL_USED, cwd=tmp_path, env=board_env(board.url))

    assert (ran.code, ran.out, ran.err) == (0, "", "")


def test_an_answer_over_one_mebibyte_is_not_read(tmp_path: Path) -> None:
    huge = json.dumps({"output": "x" * (2 << 20)}).encode()
    with FakeBoard({"/api/hooks/tell": Reply(200, huge)}) as board:
        ran = run_hook("tell", TOOL_USED, cwd=tmp_path, env=board_env(board.url))

    assert (ran.code, ran.out, ran.err) == (0, "", "")


def test_an_answer_that_never_ends_is_dropped_once_it_passes_the_limit(tmp_path: Path) -> None:
    with FakeBoard({"/api/hooks/tell": Reply(200, b'{"output": "', endless=True)}) as board:
        started = time.monotonic()
        ran = run_hook("tell", TOOL_USED, cwd=tmp_path, env=board_env(board.url))
        took = time.monotonic() - started

    assert (ran.code, ran.out, ran.err) == (0, "", "")
    assert took < 3


def test_an_answer_a_little_over_one_mebibyte_is_not_used(tmp_path: Path) -> None:
    just_over = json.dumps({"output": "x" * ((1 << 20) - 5)}).encode()
    assert len(just_over) > 1 << 20
    with FakeBoard({"/api/hooks/tell": Reply(200, just_over)}) as board:
        ran = run_hook("tell", TOOL_USED, cwd=tmp_path, env=board_env(board.url))

    assert (ran.code, ran.out, ran.err) == (0, "", "")


def test_a_board_that_stalls_is_given_five_seconds_and_no_more(tmp_path: Path) -> None:
    with FakeBoard({"/api/hooks/tell": Reply(200, b"{}", delay_s=12)}) as board:
        started = time.monotonic()
        ran = run_hook("tell", TOOL_USED, cwd=tmp_path, env=board_env(board.url))
        took = time.monotonic() - started

    assert (ran.code, ran.out, ran.err) == (0, "", "")
    assert 4.5 <= took < 8


def test_a_payload_over_one_mebibyte_is_not_sent(tmp_path: Path) -> None:
    payload = json.dumps(
        {"session_id": "s", "tool_name": "Bash", "tool_input": {"x": "y" * (2 << 20)}}
    )
    with FakeBoard({"/api/hooks/permission": Reply(200, b'{"output": "x"}')}) as board:
        ran = run_hook("permission", payload, cwd=tmp_path, env=board_env(board.url))

    assert (ran.code, ran.out) == (0, "")
    assert board.requests == []


ALLOW = (
    '{"hookSpecificOutput": {"hookEventName": "PermissionRequest", '
    '"decision": {"behavior": "allow"}}}'
)
REQUEST = {
    "session_id": "s-1",
    "hook_event_name": "PermissionRequest",
    "tool_name": "Bash",
    "tool_input": {"command": "npm test -- --watch"},
}


def test_a_permission_request_goes_to_the_board_whole_with_the_sandbox_flag(tmp_path: Path) -> None:
    reply = Reply(200, json.dumps({"output": ALLOW}).encode())
    with FakeBoard({"/api/hooks/permission": reply}) as board:
        sandboxed = run_hook(
            "permission",
            json.dumps(REQUEST),
            cwd=tmp_path,
            env={**board_env(board.url), "CODE_FACTORY_SANDBOXED": "1"},
        )
        open_host = run_hook(
            "permission", json.dumps(REQUEST), cwd=tmp_path, env=board_env(board.url)
        )

    assert (sandboxed.code, sandboxed.out, sandboxed.err) == (0, ALLOW, "")
    assert open_host.out == ALLOW
    first, second = board.requests
    assert first.body == {**REQUEST, "sandboxed": True}
    assert second.body == {**REQUEST, "sandboxed": False}


def test_a_permission_request_waits_for_the_owner_longer_than_a_tell_does(tmp_path: Path) -> None:
    reply = Reply(200, json.dumps({"output": ALLOW}).encode(), delay_s=6.5)
    with FakeBoard({"/api/hooks/permission": reply}) as board:
        ran = run_hook("permission", json.dumps(REQUEST), cwd=tmp_path, env=board_env(board.url))

    assert ran.out == ALLOW


def test_a_permission_request_with_no_answer_prints_nothing(tmp_path: Path) -> None:
    with FakeBoard({"/api/hooks/permission": Reply(204)}) as board:
        ran = run_hook("permission", json.dumps(REQUEST), cwd=tmp_path, env=board_env(board.url))

    assert (ran.code, ran.out, ran.err) == (0, "", "")


def test_recall_sends_the_folder_and_session_and_prints_the_text(tmp_path: Path) -> None:
    reply = Reply(200, json.dumps({"output": "text\n"}).encode())
    start = json.dumps({"session_id": "s-9", "cwd": str(tmp_path), "source": "startup"})
    with FakeBoard({"/api/hooks/recall": reply}) as board:
        ran = run_hook("recall", start, cwd=tmp_path, env=board_env(board.url))

    assert (ran.code, ran.out, ran.err) == (0, "text\n", "")
    assert board.requests[0].body == {"cwd": str(tmp_path), "session_id": "s-9"}


def test_recall_without_a_cwd_uses_the_process_folder_and_survives_bad_payloads(
    tmp_path: Path,
) -> None:
    reply = Reply(200, json.dumps({"output": "text\n"}).encode())
    with FakeBoard({"/api/hooks/recall": reply}) as board:
        env = board_env(board.url)
        plain = run_hook("recall", "{}", cwd=tmp_path, env=env)
        bad = run_hook("recall", "not json", cwd=tmp_path, env=env)
        listing = run_hook("recall", "[1]", cwd=tmp_path, env=env)

    assert plain.out == "text\n"
    assert (bad.out, listing.out) == ("", "")
    assert board.requests[0].body == {"cwd": str(tmp_path.resolve()), "session_id": ""}
    assert len(board.requests) == 1


def test_concurrent_tells_each_get_their_own_answer(tmp_path: Path) -> None:
    replies = {"/api/hooks/tell": tell_reply(), "/api/hooks/tell/confirm": Reply(204)}
    results: list[str] = []
    with FakeBoard(replies) as board:

        def one() -> None:
            results.append(run_hook("tell", TOOL_USED, cwd=tmp_path, env=board_env(board.url)).out)

        threads = [threading.Thread(target=one) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert results == [NEWS] * 4
