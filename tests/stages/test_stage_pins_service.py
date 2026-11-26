"""The pins a ticket's tests make on its requirements, read from a worktree, and the readers over a
ticket's ledger for screens and answers."""

from pathlib import Path

import pytest

from code_factory.stages.service import StageService
from code_factory.tickets.models import (
    DocumentName,
    DocumentWrite,
    NewActivity,
    Ticket,
    TicketFields,
)
from code_factory.tickets.service import ActivityService, DocumentService, TicketService
from stage_values import NOW
from ticket_values import OWNER

REQUIREMENTS = """\
# Requirements

## Requirements

| ID | Requirement | Source | Method | Rationale |
|---|---|---|---|---|
| R1 | It works | G1 | Test | Needed |

## Acceptance criteria

| ID | Criterion | Named check |
|---|---|---|
| R1 | Given it, then it works | test_it, test_gone |
| R2 | A person judges it | review |
| R3 | No check named |  |
"""


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    root = tmp_path / "wt"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_app.py").write_text(
        "def test_it() -> None:\n    pass\n\n\n"
        "class TestMore:\n    def test_method(self) -> None:\n        pass\n"
    )
    return root


async def test_a_pattern_matching_no_file_and_a_check_no_test_defines_are_the_gaps(
    stages: StageService,
    tickets: TicketService,
    documents: DocumentService,
    started: Ticket,
    worktree: Path,
) -> None:
    await tickets.update(
        started.id, TicketFields(tests="tests/*.py, nope/*.py", e2e="e2e/*.ts"), by=OWNER
    )
    await documents.write_document(
        started.id, DocumentName.REQUIREMENTS, DocumentWrite(content=REQUIREMENTS), by=OWNER
    )

    gaps = await stages.test_gaps(started.id, worktree)

    assert gaps == [
        "no file matches nope/*.py",
        "no file matches e2e/*.ts",
        "R1: test_gone",
        "R3: no named check",
    ]


async def test_a_ticket_with_every_pattern_matched_and_every_check_defined_has_no_gap(
    stages: StageService,
    tickets: TicketService,
    documents: DocumentService,
    started: Ticket,
    worktree: Path,
) -> None:
    await tickets.update(started.id, TicketFields(tests="tests/*.py"), by=OWNER)
    ok = REQUIREMENTS.replace("test_it, test_gone", "test_it, TestMore::test_method").replace(
        "|  |", "| review |"
    )
    await documents.write_document(
        started.id, DocumentName.REQUIREMENTS, DocumentWrite(content=ok), by=OWNER
    )

    assert await stages.test_gaps(started.id, worktree) == []


async def test_a_ticket_with_no_requirements_document_has_only_its_unmatched_patterns(
    stages: StageService, tickets: TicketService, started: Ticket, worktree: Path
) -> None:
    await tickets.update(started.id, TicketFields(tests="nope/*.py"), by=OWNER)

    assert await stages.test_gaps(started.id, worktree) == ["no file matches nope/*.py"]


async def test_a_capture_of_the_tree_waits_until_it_is_approved_or_sent_back(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    await activity.append(
        started.id, NewActivity(kind="capture", data={"tree": "t1"}, at=NOW), by="board"
    )

    waiting = await stages.capture_state(started.id, "t1")

    assert waiting is not None
    assert waiting.kind == "capture"
    assert await stages.capture_state(started.id, "t2") is None
    await activity.append(
        started.id, NewActivity(kind="capture_approved", data={"tree": "t1"}, at=NOW), by="owner"
    )
    assert await stages.capture_state(started.id, "t1") is None


async def test_an_answer_to_apply_waits_until_a_run_that_started_after_it_applied_them(
    stages: StageService, activity: ActivityService, started: Ticket
) -> None:
    await activity.append(
        started.id,
        NewActivity(kind="answer", data={"apply": True, "text": "yes"}, at=NOW),
        by="owner",
    )
    await activity.append(
        started.id, NewActivity(kind="answer", data={"apply": False}, at=NOW), by="owner"
    )

    assert [r.data["text"] for r in await stages.answers_waiting(started.id)] == ["yes"]
    await activity.append(
        started.id,
        NewActivity(kind="answers_applied", data={"started": NOW.timestamp() + 60}, at=NOW),
        by="board",
    )
    assert await stages.answers_waiting(started.id) == []
