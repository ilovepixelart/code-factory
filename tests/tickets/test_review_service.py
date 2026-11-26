"""Submitting a review: the review document and the previous implementation's finding records
(`finding` with `id` F<n> counted per ticket, `severity`, `class`, `file`, `line`, `text`, and
`rule` when named; `finding.kept` for an open finding the review continues)."""

import pytest

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.tickets.models import (
    DocumentName,
    Finding,
    FindingDismissed,
    FindingId,
    Review,
    Ticket,
)
from code_factory.tickets.service import ActivityService, DocumentService, ReviewService

RUN = "run-review"
BLOCKER = Finding(severity="blocker", text="The title is not saved", requirement_id="CF-7-R1")
NIT = Finding(severity="nit", text="A long line", path="src/a.py", line=12, rule="line-length")
CHANGES = Review(verdict="changes", summary="One gap.", findings=[BLOCKER, NIT])


async def test_a_review_writes_its_document_and_numbers_its_findings(
    reviews: ReviewService,
    documents: DocumentService,
    activity: ActivityService,
    ticket: Ticket,
) -> None:
    submitted = await reviews.submit_review(ticket.id, CHANGES, by=RUN)
    assert submitted.review_version == 1
    assert submitted.findings == [
        FindingId(id="F1", severity="blocker"),
        FindingId(id="F2", severity="nit"),
    ]
    document = await documents.get_document(ticket.id, DocumentName.REVIEW)
    assert document.body == (
        "# Review\n\nVerdict: changes\n\nOne gap.\n\n## Findings\n\n"
        "- F1 [blocker] CF-7-R1: The title is not saved\n"
        "- F2 [nit] src/a.py:12: A long line [rule: line-length]\n"
    )
    records = (await activity.list_activity(ticket.id, kinds=["finding"])).items
    assert [(r.by, r.data) for r in records] == [
        (
            RUN,
            {
                "id": "F1",
                "severity": "blocker",
                "class": "important",
                "file": "",
                "line": 0,
                "text": "The title is not saved",
                "requirement": "CF-7-R1",
            },
        ),
        (
            RUN,
            {
                "id": "F2",
                "severity": "nit",
                "class": "nit",
                "file": "src/a.py",
                "line": 12,
                "text": "A long line",
                "rule": "line-length",
            },
        ),
    ]


async def test_a_later_review_continues_the_numbering_and_keeps_a_prior_finding(
    reviews: ReviewService, activity: ActivityService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, CHANGES, by=RUN)
    kept = BLOCKER.model_copy(update={"prior_id": "F1"})
    new = Finding(severity="major", text="The save button is gone")
    again = await reviews.submit_review(
        ticket.id, Review(verdict="changes", summary="Still.", findings=[kept, new]), by=RUN
    )
    assert again.review_version == 2
    assert again.findings == [
        FindingId(id="F1", severity="blocker"),
        FindingId(id="F3", severity="major"),
    ]
    records = (await activity.list_activity(ticket.id, kinds=["finding.kept"])).items
    assert [r.data for r in records] == [{"id": "F1"}]


async def test_a_prior_finding_the_ticket_does_not_have_is_refused(
    reviews: ReviewService, ticket: Ticket
) -> None:
    unknown = BLOCKER.model_copy(update={"prior_id": "F9"})
    review = Review(verdict="changes", summary="s", findings=[unknown])
    with pytest.raises(BadRequestError, match=f"F9 is not a finding of {ticket.id}"):
        await reviews.submit_review(ticket.id, review, by=RUN)


async def test_a_refused_review_writes_nothing(
    reviews: ReviewService, documents: DocumentService, ticket: Ticket
) -> None:
    with pytest.raises(BadRequestError, match="a changes verdict needs at least one finding"):
        await reviews.submit_review(ticket.id, Review(verdict="changes", summary="s"), by=RUN)
    assert await documents.list_documents(ticket.id) == []


async def test_a_finding_is_dismissed_with_its_reason_on_the_ticket(
    reviews: ReviewService, activity: ActivityService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, CHANGES, by=RUN)
    dismissed = await reviews.dismiss_finding(
        ticket.id, "F2", "The line is generated code.", by="run-build"
    )
    assert dismissed == FindingDismissed(id="F2", reason="The line is generated code.")
    records = (await activity.list_activity(ticket.id, kinds=["finding.dismissed"])).items
    assert [(r.by, r.data) for r in records] == [
        ("run-build", {"id": "F2", "reason": "The line is generated code."})
    ]


@pytest.mark.parametrize("reason", ["", "   ", "x" * 1001])
async def test_a_dismissal_needs_a_reason_of_one_to_a_thousand_characters(
    reviews: ReviewService, ticket: Ticket, reason: str
) -> None:
    await reviews.submit_review(ticket.id, CHANGES, by=RUN)
    with pytest.raises(BadRequestError, match="a dismissal needs a reason of 1 to 1000 characters"):
        await reviews.dismiss_finding(ticket.id, "F1", reason, by="run-build")


async def test_a_finding_the_ticket_does_not_have_cannot_be_dismissed(
    reviews: ReviewService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, CHANGES, by=RUN)
    with pytest.raises(BadRequestError, match=f"F9 is not a finding of {ticket.id}"):
        await reviews.dismiss_finding(ticket.id, "F9", "Not a problem.", by="run-build")


async def test_a_finding_is_dismissed_once(
    reviews: ReviewService, activity: ActivityService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, CHANGES, by=RUN)
    await reviews.dismiss_finding(ticket.id, "F1", "Out of scope.", by="run-build")
    with pytest.raises(ConflictError, match=r"F1 is already dismissed: Out of scope\."):
        await reviews.dismiss_finding(ticket.id, "F1", "Again.", by="run-build")
    assert len((await activity.list_activity(ticket.id, kinds=["finding.dismissed"])).items) == 1


async def test_a_ticket_that_does_not_exist_has_no_findings_to_dismiss(
    reviews: ReviewService,
) -> None:
    with pytest.raises(NotFoundError, match="CF-999999"):
        await reviews.dismiss_finding("CF-999999", "F1", "Nope.", by="run-build")


async def test_a_review_version_is_never_reused_after_its_document_is_deleted(
    reviews: ReviewService, documents: DocumentService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, CHANGES, by=RUN)
    await documents.delete_document(ticket.id, DocumentName.REVIEW, by="owner")
    again = await reviews.submit_review(ticket.id, CHANGES, by=RUN)
    assert again.review_version == 2
    assert [f.id for f in await reviews.review_findings(ticket.id, 1)] == ["F1", "F2"]


async def test_a_review_names_a_prior_finding_once(
    reviews: ReviewService, activity: ActivityService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, CHANGES, by=RUN)
    twice = BLOCKER.model_copy(update={"prior_id": "F1"})
    review = Review(verdict="changes", summary="s", findings=[twice, twice])
    with pytest.raises(BadRequestError, match="F1 is named twice in one review"):
        await reviews.submit_review(ticket.id, review, by=RUN)
    assert (await activity.list_activity(ticket.id, kinds=["finding.kept"])).items == []
