"""What the permission hook prints for the agent's runtime: the answer to one request."""

from typing import Any

RETRY_WORDS = (
    "Nobody answered this permission request from the board in time; do it another way "
    "inside your worktree, or ask in the ticket's Open questions."
)
OWNER_DENIED = "The owner denied this request."
REVIEWER_DENIED = "The permission reviewer denied this: "


def hook_output(*, allow: bool, message: str = "", interrupt: bool = False) -> dict[str, Any]:
    """The hook's JSON: an allow, or a deny with its words.

    An owner's deny interrupts the run; one the board settles itself (policy, reviewer, no
    answer in time) does not, so the run reads the words and tries another way.
    """
    decision: dict[str, Any] = {"behavior": "allow" if allow else "deny"}
    if not allow:
        decision["message"] = message
        if interrupt:
            decision["interrupt"] = True
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}
