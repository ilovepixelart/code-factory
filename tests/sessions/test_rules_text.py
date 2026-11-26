import json

from code_factory.sessions.models import Event
from code_factory.sessions.rules import derive
from code_factory.sessions.rules import timeline as rules_timeline


def event(seq: int, name: str, **payload: object) -> Event:
    return Event(seq, "s", None, name, float(seq), "s.jsonl", seq, dict(payload))


def test_a_prompt_trimmed_at_capture_shows_its_head_with_an_ellipsis() -> None:
    marker = {"_trimmed_chars": 4000, "head": "Fix the long"}
    view = derive.derive_unsettled([event(1, "UserPromptSubmit", prompt=marker)])
    assert view is not None
    assert view.last_prompt == "Fix the long…"
    entry = rules_timeline.timeline([event(1, "UserPromptSubmit", prompt=marker)])[0]
    assert (entry.kind, entry.detail) == ("prompt", "Fix the long…")


def test_an_object_that_is_no_trim_marker_is_no_text() -> None:
    view = derive.derive_unsettled([event(1, "UserPromptSubmit", prompt={"head": "x"})])
    assert view is not None
    assert view.last_prompt == ""


def test_a_view_holds_no_nul_and_no_lone_surrogate_whatever_the_payload_did() -> None:
    nasty = "a\x00b\ud800c"
    events = [
        event(
            1,
            "SessionStart",
            cwd=f"/w{nasty}",
            transcript_path=f"/t{nasty}",
        ),
        event(2, "UserPromptSubmit", prompt=f"p{nasty}"),
        event(
            3,
            "PreToolUse",
            tool_name=f"Bash{nasty}",
            tool_use_id=f"id{nasty}",
            tool_input={"command": f"ls {nasty}"},
        ),
    ]
    view = derive.derive_unsettled(events)
    assert view is not None
    dumped = view.model_dump_json()
    assert "\\u0000" not in dumped
    assert "\\ud800" not in dumped
    assert view.cwd == "/wa�b?c"
    assert view.last_prompt == "pa�b?c"
    assert view.current_action is not None
    assert view.current_action.summary == "ls a�b?c"
    json.dumps(view.model_dump())
    view.last_prompt.encode("utf-8")


def test_a_plan_item_holds_no_nul_either() -> None:
    todos = [{"content": "do\x00 it\ud800", "status": "pending"}]
    plan = event(
        1, "PreToolUse", tool_name="TodoWrite", tool_use_id="p", tool_input={"todos": todos}
    )
    view = derive.derive_unsettled([plan])
    assert view is not None
    assert view.plan == "plan 1/1: do\ufffd it?"
