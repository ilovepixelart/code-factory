"""The JSON a hook prints for the runtime: one line, the previous layout, ASCII only."""

import json

from code_factory.hooks.rules.output import permission, rewrite_denied, tell
from code_factory.hooks.rules.tell import eligible


def test_a_rewrite_denial_is_one_line_with_the_default_separators() -> None:
    assert rewrite_denied("code-factory: refused `git push -f`: no.") == (
        '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", '
        '"permissionDecisionReason": "code-factory: refused `git push -f`: no."}}'
    )


def test_news_is_given_as_additional_context_for_the_event_that_asked() -> None:
    assert tell("PostToolUseFailure", "owner commented on CF-5: Keep it small") == (
        '{"hookSpecificOutput": {"hookEventName": "PostToolUseFailure", '
        '"additionalContext": "owner commented on CF-5: Keep it small"}}'
    )


def test_text_that_is_not_ascii_is_escaped_so_it_survives_the_runtime() -> None:
    said = tell("PostToolUse", "café \u2014 ok")

    assert "\\u00e9" in said
    assert said.isascii()
    assert json.loads(said)["hookSpecificOutput"]["additionalContext"] == "café \u2014 ok"


def test_an_allow_has_no_message() -> None:
    assert permission("allow") == (
        '{"hookSpecificOutput": {"hookEventName": "PermissionRequest", '
        '"decision": {"behavior": "allow"}}}'
    )


def test_a_policy_refusal_has_a_message_and_no_interrupt() -> None:
    assert permission("deny", "outside your worktree") == (
        '{"hookSpecificOutput": {"hookEventName": "PermissionRequest", '
        '"decision": {"behavior": "deny", "message": "outside your worktree"}}}'
    )


def test_an_owner_denial_interrupts_the_run() -> None:
    assert permission("deny", "The owner denied this from the board.", interrupt=True) == (
        '{"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": '
        '{"behavior": "deny", "message": "The owner denied this from the board.", '
        '"interrupt": true}}}'
    )


def test_only_the_events_after_a_tool_result_are_given_news() -> None:
    assert eligible("PostToolUse", "s-1")
    assert eligible("PostToolUseFailure", "s-1")
    assert not eligible("PreToolUse", "s-1")
    assert not eligible("UserPromptSubmit", "s-1")
    assert not eligible("PostToolUse", "")
