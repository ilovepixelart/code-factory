"""The `board` sample: what the browser tests and the contract tests rely on."""

from typing import Any

_BUG_IN_FLIGHT = "A bug in flight"

_SPECS_WRITTEN = "Specs written"

# The owner's session in every sample: 32 bytes of 0x2a, so the browser tests can send it as the
# cookie without asking the board for a link. Meaningful only in a throwaway schema.
OWNER_ENTROPY = bytes([0x2A]) * 32

LONG_DESCRIPTION = " ".join(["A description long enough to be cut."] * 12)

# Tickets in filing order (numbers come from the sequence: CF-1 first). `parent` and `blocked_by`
# name a title filed earlier; `branch` and `merged` are the facts the column is read from.
BOARD_TICKETS: tuple[dict[str, Any], ...] = (
    {
        "repository": "sample",
        "title": _SPECS_WRITTEN,
        "labels": ["docs"],
        "description": "The first.",
    },
    {
        "repository": "sample",
        "title": _BUG_IN_FLIGHT,
        "type": "bug",
        "labels": ["ui", "agents"],
        "priority": "high",
        "assignee": "alex",
        "blocked": "waiting on design",
        "due": "2026-10-10",
        "budget": "2.5",
        "description": LONG_DESCRIPTION,
        "parent": _SPECS_WRITTEN,
        "branch": "ticket/cf-2",
    },
    {
        "repository": "sample",
        "title": "Worked on main",
        "labels": ["agents"],
        "priority": "low",
        "parent": _SPECS_WRITTEN,
        "blocked_by": [_BUG_IN_FLIGHT],
    },
    {"repository": "sample", "title": "Archived", "archived": True},
    {"repository": "sample", "title": "Merged already", "merged": True},
    {"repository": "second", "title": "Elsewhere", "priority": "medium", "labels": ["ops"]},
    {"repository": "second", "title": "Other repository, second", "labels": ["ui"]},
)

# Documents by the title of the ticket that holds them.
BOARD_DOCUMENTS: dict[str, dict[str, str]] = {
    _SPECS_WRITTEN: {
        "requirements": (
            "# CF-1 product requirements\n\n## Requirements\n\n"
            "| ID | Requirement | Named check |\n|---|---|---|\n"
            "| CF-1-R1 | The first requirement | review |\n"
        ),
        "spec": "# Spec\n\nProblem.\n\n## Open questions\n\n- Which colour?\n",
        "uat": "# UAT\n\nCases.\n",
    },
    _BUG_IN_FLIGHT: {"spec": "# Spec\n\nStarted.\n"},
}

BOARD_MEMORY: tuple[dict[str, str], ...] = (
    {"kind": "rule", "statement": "Keep it small and test first", "source": "conversation"},
    {"kind": "lesson", "statement": "The gate ran twice on one tree", "source": "CF-2"},
    {"kind": "decision", "statement": "Ship small pull requests", "source": "chat"},
)
