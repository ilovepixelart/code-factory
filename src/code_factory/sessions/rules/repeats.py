"""The check step that failed for the same reason in several sessions, found from tool output.

A proposal's words come from the step, the exit code and the count, never from text a session wrote.
"""

from collections.abc import Sequence

from code_factory.sessions.models import Failure, Recurrence

# The distinct sessions a failure must appear in before it is proposed.
THRESHOLD = 3
CODE_DIGITS = 3  # an exit code is at most 255
_STEP_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")


def _failure(line: str) -> Failure | None:
    rest = line.strip().removeprefix("gate: ")
    if rest == line.strip():
        return None
    step, _, tail = rest.partition(" ")
    code = tail.removeprefix("failed (exit ").removesuffix(")")
    if tail == code or not step or not set(step) <= _STEP_CHARACTERS:
        return None
    if not code.isascii() or not code.isdigit() or len(code) > CODE_DIGITS:
        return None
    return Failure(step, int(code))


def printed(value: object) -> str:
    """The text of a tool output as the ledger holds it.

    Whole when it was short; a string trimmed at capture holds only the gate lines it kept, and an
    object (`tool_response`) is its `stdout` and `stderr`.
    """
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    gates = value.get("gates")
    if isinstance(gates, list):
        return "\n".join(str(line) for line in gates if isinstance(line, str))
    return "\n".join(part for key in ("stdout", "stderr") if (part := printed(value.get(key))))


def output_text(tool_response: object, error: object) -> str:
    """Everything a Bash result printed: its `tool_response` and the `error` of a failure."""
    return "\n".join((printed(tool_response), printed(error)))


def failures(output: str) -> list[Failure]:
    """The failures a tool printed: each line that is exactly `gate: <step> failed (exit <code>)`.

    A line that only quotes one inside other words, or names a quarantined or flaky step, is none.
    """
    return [found for line in output.splitlines() if (found := _failure(line)) is not None]


def recurring(sessions: Sequence[tuple[str, Sequence[Failure]]]) -> list[Recurrence]:
    """The failures seen in at least three of the sessions, ordered by step and code.

    A session counts once however often it failed.
    """
    seen: dict[Failure, set[str]] = {}
    for session_id, failed in sessions:
        for failure in failed:
            seen.setdefault(failure, set()).add(session_id)
    return [
        Recurrence(failure, sorted(ids))
        for failure, ids in sorted(seen.items(), key=lambda item: (item[0].step, item[0].code))
        if len(ids) >= THRESHOLD
    ]


def statement(failure: Failure) -> str:
    """The memory statement for a recurrence; one per step and code, whatever the count."""
    return (
        f"The check step {failure.step} failed with exit {failure.code} in several sessions: "
        "run `sh scripts/gate.sh --reached` and read its result before committing."
    )
