"""When a session is told what was said on its ticket."""

TOOL_RESULTS = ("PostToolUse", "PostToolUseFailure")


def eligible(event: str, session_id: str) -> bool:
    """Whether the hook event is a tool's result of a session that has an id.

    A session the board did not start has no ticket and is given nothing; before a tool call the
    runtime takes no added context.
    """
    return event in TOOL_RESULTS and bool(session_id)
