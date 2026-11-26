"""The guarantees the board makes of a run, and where a runtime does not keep one.

Nothing else may be missing: the runs module observes real starts against this table.
"""

from code_factory.agents.models.constants import GUARANTEES

_PERMISSIONS = GUARANTEES[1]

GAPS = (
    (
        "codex",
        _PERMISSIONS,
        (
            "Codex runs with the board's worktree sandbox and approval policy set to never. "
            "The Codex CLI declines native permission requests without sending them to the Inbox. "
            "Ticket questions can still reach the Inbox through the board's MCP tools."
        ),
    ),
)


def gaps_of(runtime: str) -> list[dict[str, str]]:
    """The guarantees `runtime` lacks, each with why, in the table's order."""
    return [{"guarantee": guarantee, "why": why} for of, guarantee, why in GAPS if of == runtime]
