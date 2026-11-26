"""exceptions.toml held to its model, the tool files and lockfiles it speaks for, and the date."""

from dataclasses import dataclass, field
from datetime import date

from code_factory.settings.models.problems import ExceptionsReport
from code_factory.settings.rules.entries import exception_tickets, read_exceptions
from code_factory.settings.rules.expiry import expired_problems, expiry_fails
from code_factory.settings.rules.quarantine import quarantine_problems
from code_factory.settings.rules.tool_files import (
    ToolFiles,
    shared_branch_problems,
    stale_problems,
    unlisted_problems,
)

__all__ = [
    "ExceptionFacts",
    "exception_tickets",
    "exceptions_problems",
    "expiry_fails",
]


@dataclass(frozen=True)
class ExceptionFacts:
    """What a service resolved before the rules run, so the rules do no IO.

    `tickets` holds the existing ones among those `exception_tickets` named (None: not checked);
    `locked` the `(lockfile, package)` pairs a lockfile resolves; `sharing` the tickets that share
    a branch with each ticket; `tests` whether each quarantined test is defined in a tracked file;
    `expiry_fails` the answer of `expiry_fails`.
    """

    tickets: frozenset[str] | None
    expiry_fails: bool
    tools: ToolFiles = field(default_factory=ToolFiles)
    locked: frozenset[tuple[str, str]] = frozenset()
    sharing: dict[str, tuple[str, ...]] = field(default_factory=dict)
    tests: dict[str, bool] = field(default_factory=dict)


def exceptions_problems(text: str, today: date, facts: ExceptionFacts) -> ExceptionsReport:
    """Every problem of exceptions.toml, and the expired entries a branch passes as notes."""
    entries, problems = read_exceptions(text, facts.tickets)
    problems += facts.tools.problems
    problems += unlisted_problems(entries, facts.tools)
    for entry in entries:
        if entry.kind == "quarantine":
            problems += quarantine_problems(text, entry, facts.tests.get(entry.name, False))
        else:
            problems += stale_problems(entry, facts.tools, facts.locked)
    problems += shared_branch_problems(entries, facts.sharing)
    ended, notes = expired_problems(entries, today, fails=facts.expiry_fails)
    return ExceptionsReport(problems=tuple(sorted([*problems, *ended])), notes=tuple(sorted(notes)))
