"""Where each finding of a ticket stands: open, fixed or dismissed.

The states follow the previous implementation's findings list: `open` until closed as `fixed` or
`dismissed` with a reason; the list shows blocking (`important`) findings first, then nits, each
group in the order opened; a later review closes as fixed what it no longer raises.
"""

import pytest

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.tickets.models import (
    Finding,
    FindingState,
    Review,
    ReviewRecord,
    Ticket,
)
from code_factory.tickets.service import ActivityService, ReviewService
from ticket_values import NOW

RUN = "run-review"
BLOCKER = Finding(severity="blocker", text="The title is not saved", requirement_id="CF-7-R1")
NIT = Finding(severity="nit", text="A long line", path="src/a.py", line=12, rule="line-length")
MAJOR = Finding(severity="major", text="The save button is gone")


def changes(*findings: Finding) -> Review:
    return Review(verdict="changes", summary="s", findings=list(findings))


def standing(found: list[FindingState]) -> list[tuple[str, str]]:
    return [(f.id, f.state) for f in found]


async def test_a_new_finding_is_open_and_the_list_shows_blocking_ones_first(
    reviews: ReviewService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, changes(NIT, BLOCKER), by=RUN)
    found = await reviews.list_findings(ticket.id)
    assert standing(found) == [("F2", "open"), ("F1", "open")]
    assert found[1].model_dump() == {
        "id": "F1",
        "severity": "nit",
        "finding_class": "nit",
        "file": "src/a.py",
        "line": 12,
        "text": "A long line",
        "rule": "line-length",
        "requirement": "",
        "state": "open",
        "reason": "",
        "by": "",
    }


async def test_a_ticket_without_a_review_has_no_findings(
    reviews: ReviewService, ticket: Ticket
) -> None:
    assert await reviews.list_findings(ticket.id) == []


async def test_a_ticket_that_does_not_exist_has_no_findings_list(reviews: ReviewService) -> None:
    with pytest.raises(NotFoundError, match="CF-999999"):
        await reviews.list_findings("CF-999999")


async def test_closing_a_finding_as_fixed_records_who_and_why(
    reviews: ReviewService, activity: ActivityService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, changes(BLOCKER, NIT), by=RUN)
    closed = await reviews.close_finding(ticket.id, "F1", "fixed", "  Saved now.  ", by="owner")
    assert (closed.id, closed.state, closed.reason, closed.by) == (
        "F1",
        "fixed",
        "Saved now.",
        "owner",
    )
    assert standing(await reviews.list_findings(ticket.id)) == [("F1", "fixed"), ("F2", "open")]
    records = (await activity.list_activity(ticket.id, kinds=["finding.closed"])).items
    assert [(r.by, r.data) for r in records] == [
        ("owner", {"id": "F1", "state": "fixed", "reason": "Saved now."})
    ]


async def test_the_owner_can_close_a_finding_as_dismissed(
    reviews: ReviewService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, changes(BLOCKER), by=RUN)
    await reviews.close_finding(ticket.id, "F1", "dismissed", "Out of scope.", by="owner")
    [finding] = await reviews.list_findings(ticket.id)
    assert (finding.state, finding.reason, finding.by) == ("dismissed", "Out of scope.", "owner")


async def test_a_dismissal_by_a_run_shows_in_the_list_with_its_reason(
    reviews: ReviewService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, changes(NIT), by=RUN)
    await reviews.dismiss_finding(ticket.id, "F1", "Generated code.", by="run-build")
    [finding] = await reviews.list_findings(ticket.id)
    assert (finding.state, finding.reason, finding.by) == (
        "dismissed",
        "Generated code.",
        "run-build",
    )


@pytest.mark.parametrize(
    ("close", "error", "message"),
    [
        (("F1", "fixed", "  "), BadRequestError, "a closed finding needs a reason"),
        (("F1", "open", "why"), BadRequestError, "a finding closes as fixed or dismissed"),
        (("F9", "fixed", "why"), NotFoundError, "no finding F9 on CF-"),
    ],
)
async def test_a_close_that_cannot_be_taken_says_why(
    reviews: ReviewService,
    ticket: Ticket,
    close: tuple[str, str, str],
    error: type[Exception],
    message: str,
) -> None:
    await reviews.submit_review(ticket.id, changes(BLOCKER), by=RUN)
    finding, state, reason = close
    with pytest.raises(error, match=message):
        await reviews.close_finding(ticket.id, finding, state, reason, by="owner")
    assert standing(await reviews.list_findings(ticket.id)) == [("F1", "open")]


async def test_a_finding_closed_already_is_refused_with_how_it_was_closed(
    reviews: ReviewService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, changes(BLOCKER), by=RUN)
    await reviews.close_finding(ticket.id, "F1", "fixed", "Saved now.", by="owner")
    with pytest.raises(ConflictError, match=r"F1 is already fixed: Saved now\."):
        await reviews.close_finding(ticket.id, "F1", "dismissed", "Again.", by="owner")
    await reviews.submit_review(ticket.id, changes(NIT), by=RUN)
    await reviews.dismiss_finding(ticket.id, "F2", "Generated code.", by="run-build")
    with pytest.raises(ConflictError, match=r"F2 is already dismissed: Generated code\."):
        await reviews.close_finding(ticket.id, "F2", "fixed", "Done.", by="owner")


async def test_a_later_review_closes_as_fixed_what_it_no_longer_raises(
    reviews: ReviewService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, changes(BLOCKER, NIT), by=RUN)
    kept = BLOCKER.model_copy(update={"prior_id": "F1"})
    await reviews.submit_review(ticket.id, changes(kept), by="run-review-2")
    found = {f.id: f for f in await reviews.list_findings(ticket.id)}
    assert (found["F1"].state, found["F2"].state) == ("open", "fixed")
    assert (found["F2"].reason, found["F2"].by) == (
        "the review no longer raises it",
        "run-review-2",
    )


async def test_a_passing_review_closes_every_open_finding(
    reviews: ReviewService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, changes(BLOCKER), by=RUN)
    await reviews.submit_review(ticket.id, Review(verdict="pass", summary="Good."), by=RUN)
    assert standing(await reviews.list_findings(ticket.id)) == [("F1", "fixed")]


async def test_a_review_that_keeps_a_dismissed_finding_reopens_it(
    reviews: ReviewService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, changes(BLOCKER), by=RUN)
    await reviews.dismiss_finding(ticket.id, "F1", "Out of scope.", by="run-build")
    kept = BLOCKER.model_copy(update={"prior_id": "F1"})
    await reviews.submit_review(ticket.id, changes(kept), by=RUN)
    [finding] = await reviews.list_findings(ticket.id)
    assert (finding.state, finding.reason) == ("open", "")
    await reviews.dismiss_finding(ticket.id, "F1", "Still out of scope.", by="run-build")
    assert standing(await reviews.list_findings(ticket.id)) == [("F1", "dismissed")]


async def test_a_dismissed_finding_a_later_review_does_not_cite_stays_dismissed(
    reviews: ReviewService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, changes(BLOCKER), by=RUN)
    await reviews.dismiss_finding(ticket.id, "F1", "Out of scope.", by="run-build")
    await reviews.submit_review(ticket.id, changes(MAJOR), by=RUN)
    assert standing(await reviews.list_findings(ticket.id)) == [("F1", "dismissed"), ("F2", "open")]


async def test_blocking_findings_are_the_open_important_ones(
    reviews: ReviewService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, changes(BLOCKER, NIT, MAJOR), by=RUN)
    await reviews.close_finding(ticket.id, "F3", "fixed", "Restored.", by="owner")
    assert [f.id for f in await reviews.blocking_findings(ticket.id)] == ["F1"]


async def test_the_findings_of_a_review_version_are_those_it_raised_or_kept(
    reviews: ReviewService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, changes(BLOCKER, NIT), by=RUN)
    kept = BLOCKER.model_copy(update={"prior_id": "F1"})
    await reviews.submit_review(ticket.id, changes(kept, MAJOR), by=RUN)
    first = await reviews.review_findings(ticket.id, 1)
    second = await reviews.review_findings(ticket.id, 2)
    assert standing(first) == [("F1", "open"), ("F2", "fixed")]
    assert standing(second) == [("F1", "open"), ("F3", "open")]
    assert await reviews.review_findings(ticket.id, 3) == []


async def test_the_latest_review_names_its_version_verdict_and_author(
    reviews: ReviewService, ticket: Ticket
) -> None:
    assert await reviews.latest_review(ticket.id) is None
    await reviews.submit_review(ticket.id, changes(BLOCKER), by=RUN)
    await reviews.submit_review(ticket.id, Review(verdict="pass", summary="Good."), by="run-two")
    assert await reviews.latest_review(ticket.id) == ReviewRecord(
        version=2, verdict="pass", at=NOW, by="run-two"
    )


async def test_a_review_that_keeps_a_finding_at_a_new_severity_changes_what_blocks(
    reviews: ReviewService, ticket: Ticket
) -> None:
    await reviews.submit_review(ticket.id, changes(NIT), by=RUN)
    assert await reviews.blocking_findings(ticket.id) == []
    raised = NIT.model_copy(update={"prior_id": "F1", "severity": "blocker"})
    await reviews.submit_review(ticket.id, changes(raised), by=RUN)
    [blocking] = await reviews.blocking_findings(ticket.id)
    assert (blocking.id, blocking.severity, blocking.finding_class) == (
        "F1",
        "blocker",
        "important",
    )
