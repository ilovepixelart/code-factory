"""The merged activity feed: one entry model, a sentence for each record this module writes, and
the merge of feeds that other modules contribute (talk, delivery, checks).

Sentences are worked by hand from the record keys the previous implementation wrote.
"""

from datetime import UTC, datetime

import pytest

from code_factory.tickets.models import ActivityEntry, NewActivity, Ticket
from code_factory.tickets.service import ActivityService, describe, merge_entries
from ticket_values import OWNER


@pytest.mark.parametrize(
    ("kind", "data", "sentence"),
    [
        ("created", {"type": "bug"}, "Created as a bug"),
        ("edited", {"fields": ["title", "labels"]}, "Edited title, labels"),
        ("stage", {"from": "spec", "to": "build"}, "Moved from Spec to Build"),
        ("stage", {"from": "build", "to": "merged"}, "Moved from Build to Merged"),
        ("archived", {}, "Archived"),
        ("restored", {}, "Put back on the board"),
        ("document", {"name": "spec", "version": 3}, "Wrote the spec (version 3)"),
        ("document", {"name": "uat", "version": 1}, "Wrote the UAT plan (version 1)"),
        ("document", {"name": "requirements", "version": 2}, "Wrote the requirements (version 2)"),
        ("document", {"name": "spec", "removed": True}, "Removed the spec"),
        ("document", {"name": "draft", "version": 1}, "Wrote draft (version 1)"),
        ("mock_file", {"name": "home.png", "size": 10}, "Kept the mock image home.png"),
        ("mock_file", {"name": "home.png", "removed": True}, "Removed the mock image home.png"),
        (
            "finding",
            {"id": "F1", "severity": "blocker", "text": "The title is not saved"},
            "Review found F1 (blocker): The title is not saved",
        ),
        ("finding.kept", {"id": "F1"}, "Review kept F1"),
        ("finding.dismissed", {"id": "F2", "reason": "Generated."}, "Dismissed F2: Generated."),
        (
            "finding.closed",
            {"id": "F1", "state": "fixed", "reason": "Saved now."},
            "Closed F1 as fixed: Saved now.",
        ),
        ("review_submitted", {"verdict": "changes", "version": 2}, "Review 2 asked for changes"),
        ("review_submitted", {"verdict": "pass", "version": 1}, "Review 1 passed"),
        ("note", {"text": "Check the cache"}, "Check the cache"),
        ("diagnosis", {"text": "Stuck on review"}, "Diagnosis: Stuck on review"),
        (
            "coordinator_edit",
            {"name": "priority", "from": "low", "to": "high"},
            "The coordinator set priority from low to high",
        ),
        ("field", {"name": "priority", "value": "high"}, "Set priority to high"),
        ("field", {"name": "blocked_by", "value": "CF-3, CF-4"}, "Set blocked by to CF-3, CF-4"),
        ("field", {"name": "e2e", "value": "e2e/*.spec.ts"}, "Set E2E tests to e2e/*.spec.ts"),
        ("field", {"name": "due", "value": ""}, "Cleared due"),
        ("field", {"name": "description", "value": ""}, "Edited the description"),
        ("field", {"name": "rank", "value": "2"}, "Set rank to 2"),
        ("checks", {"exit_code": 0, "commit": "abc"}, "Checks passed"),
        ("checks", {"exit_code": 1, "reason": "2 tests failed"}, "Checks failed: 2 tests failed"),
        ("checks", {"exit_code": 2}, "Checks failed"),
        ("checks", {"exit_code": 0, "scope": "fast"}, "Fast checks passed"),
        ("checks", {"exit_code": 137}, "Checks stopped without a verdict"),
        ("checks", {"exit_code": -1}, "Checks stopped without a verdict"),
        ("checks", {"exit_code": 0, "outcome": "killed"}, "Checks stopped without a verdict"),
        ("checks", {}, "Checks stopped without a verdict"),
        ("capture", {"tree": "t", "images": ["a.png", "b.png"]}, "Captured 2 screens"),
        ("capture", {"tree": "t", "images": ["a.png"]}, "Captured 1 screen"),
        ("capture_approved", {"tree": "t"}, "Approved the screens"),
        (
            "capture_changes",
            {"tree": "t", "reason": "Wider margins"},
            "Sent the screens back: Wider margins",
        ),
        ("run.started", {}, "Run started"),
        ("attempts_judged", {}, "Attempts judged"),
    ],
)
def test_each_record_reads_as_a_sentence(kind: str, data: dict[str, object], sentence: str) -> None:
    assert describe(kind, data) == sentence


def test_a_record_missing_its_keys_still_reads_as_a_sentence() -> None:
    assert describe("stage", {}) == "Moved"
    assert describe("document", {}) == "Wrote a document"


def entry(at: int, kind: str, source: str) -> ActivityEntry:
    when = datetime(2026, 10, 4, 10, at, tzinfo=UTC)
    return ActivityEntry(at=when, kind=kind, by="", sentence=kind, data={}, source=source)


def test_feeds_merge_by_moment_and_keep_their_own_order_on_a_tie() -> None:
    tickets = [entry(1, "created", "tickets"), entry(5, "stage", "tickets")]
    talk = [entry(3, "comment", "talk"), entry(5, "answer", "talk")]
    checks = [entry(0, "checks", "checks")]
    merged = merge_entries([tickets, talk, checks])
    assert [(e.source, e.kind) for e in merged] == [
        ("checks", "checks"),
        ("tickets", "created"),
        ("talk", "comment"),
        ("tickets", "stage"),
        ("talk", "answer"),
    ]
    newest = merge_entries([tickets, talk, checks], newest_first=True)
    assert [(e.source, e.kind) for e in newest] == [
        ("tickets", "stage"),
        ("talk", "answer"),
        ("talk", "comment"),
        ("tickets", "created"),
        ("checks", "checks"),
    ]


async def test_a_tickets_records_become_entries_of_its_own_source(
    activity: ActivityService, ticket: Ticket
) -> None:
    await activity.append(ticket.id, NewActivity(kind="run.started", data={}), by="board")
    entries = await activity.entries(ticket.id)
    assert [(e.kind, e.by, e.sentence, e.source) for e in entries] == [
        ("created", OWNER, "Created as a feature", "tickets"),
        ("run.started", "board", "Run started", "tickets"),
    ]


@pytest.mark.parametrize("fields", [None, 3, "title", {"a": 1}])
def test_an_edit_record_with_malformed_fields_still_reads_as_a_sentence(fields: object) -> None:
    assert describe("edited", {"fields": fields}) == "Edited"
