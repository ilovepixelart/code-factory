"""When an entry of exceptions.toml ends, and whether a branch fails on it."""

from datetime import date

from code_factory.settings.models.problems import Problem
from code_factory.settings.rules.entries import ExceptionEntry
from code_factory.settings.rules.tool_files import EXCEPTIONS_FILE, file_name

_WATCHED_NAMES = {
    "deny.toml",
    "pnpm-workspace.yaml",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "uv.lock",
}


def _watched(path: str) -> bool:
    return path == EXCEPTIONS_FILE or file_name(path) in _WATCHED_NAMES


def expiry_fails(base: str | None, head: str | None, changed: tuple[str, ...] | None) -> bool:
    """Whether an expired entry fails this run.

    It does on main's own tree (no fork point, or HEAD is the fork point) and on a branch that
    changed an exception, an ignore or a locked version since its fork point. A branch that
    changed none of them passes with a note.
    """
    if base is None or head == base or changed is None:
        return True
    return any(_watched(path) for path in changed)


def expired_problems(
    entries: list[ExceptionEntry], today: date, *, fails: bool
) -> tuple[list[Problem], list[Problem]]:
    """The expired entries as `(problems, notes)`: `expires` is the first day an entry fails."""
    found = [
        Problem(
            EXCEPTIONS_FILE,
            entry.expires_line,
            f"{entry.name} expired on {entry.expires.isoformat()}"
            + ("" if fails else "; main's own run fails on it"),
        )
        for entry in entries
        if today >= entry.expires
    ]
    return (found, []) if fails else ([], found)
