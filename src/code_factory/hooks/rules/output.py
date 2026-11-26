"""The JSON a hook prints for the agent's runtime: one line, the previous layout, ASCII only.

Imports only `json`: the launcher loads it to print a rewrite refusal.
"""

import json


def rewrite_denied(reason: str) -> str:
    """The answer that stops a shell command before it runs."""
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


def tell(event: str, text: str) -> str:
    """What was said on the ticket, given to the session after a tool result."""
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def permission(behavior: str, message: str = "", *, interrupt: bool = False) -> str:
    """The answer to a permission request: an allow, or a deny with its words.

    An owner's deny interrupts the run; one the board settles itself does not, so the run reads
    the words and tries another way.
    """
    decision: dict[str, object] = {"behavior": behavior}
    if behavior != "allow":
        decision["message"] = message
        if interrupt:
            decision["interrupt"] = True
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}
    )


UNANSWERED = (
    "Nobody answered this permission request from the board in time; do it another way "
    "inside your worktree, or ask in the ticket's Open questions."
)


def rendered(value: object) -> str:
    """JSON in the layout of every answer above."""
    return json.dumps(value)
