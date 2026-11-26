"""A review of a ticket's branch: the review document and one record per finding."""

from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.tickets.models import (
    DocumentName,
    Finding,
    FindingDismissed,
    FindingId,
    FindingState,
    Review,
    ReviewRecord,
    ReviewSubmitted,
)
from code_factory.tickets.repository import DocumentRepository, TicketRepository
from code_factory.tickets.rules import (
    FIXED_BY_LATER_REVIEW,
    blocking,
    check_reason,
    check_review,
    finding_class,
    findings_of,
    listing_order,
    render_review,
    ticket_id,
    ticket_number,
)
from code_factory.tickets.service.common import not_found, utc_now
from code_factory.tickets.tables import TicketActivityRow, TicketDocumentRow

CLOSED_STATES = ("fixed", "dismissed")


async def _standing(tickets: TicketRepository, number: int) -> list[FindingState]:
    trail = await tickets.finding_trail(number)
    return findings_of((row.kind, row.by, row.data) for row in trail)[0]


async def _write_findings(
    tickets: TicketRepository,
    when: tuple[int, datetime, str],
    review: Review,
    known: tuple[list[str], list[FindingState]],
) -> None:
    """Close what the review no longer raises, then record each finding it lists."""
    number, now, by = when
    ids, before = known
    for finding in before:
        if finding.state == "open" and finding.id not in ids:
            closed = {"id": finding.id, "state": "fixed", "reason": FIXED_BY_LATER_REVIEW}
            await tickets.append_activity(number, (now, "finding.closed", by), closed)
    earlier = {f.id: f for f in before}
    for finding, finding_id in zip(review.findings, ids, strict=True):
        if not finding.prior_id:
            record = finding_record(finding, finding_id)
            await tickets.append_activity(number, (now, "finding", by), record)
            continue
        kept: dict[str, Any] = {"id": finding_id}
        if earlier[finding_id].severity != finding.severity:
            kept["severity"] = finding.severity
        await tickets.append_activity(number, (now, "finding.kept", by), kept)


def _not_open(finding: FindingState) -> ConflictError:
    return ConflictError(f"{finding.id} is already {finding.state}: {finding.reason}")


def finding_record(finding: Finding, finding_id: str) -> dict[str, Any]:
    """A `finding` record's data, in the previous implementation's keys."""
    data: dict[str, Any] = {
        "id": finding_id,
        "severity": finding.severity,
        "class": finding_class(finding.severity),
        "file": finding.path,
        "line": finding.line,
        "text": finding.text.strip(),
    }
    if finding.requirement_id:
        data["requirement"] = finding.requirement_id
    if finding.rule:
        data["rule"] = finding.rule
    if finding.note_id is not None:
        data["note_id"] = finding.note_id
    return data


async def _validate_notes(tickets: TicketRepository, number: int, review: Review) -> None:
    references = [f for f in review.findings if f.note_id is not None]
    if not references:
        return
    ids = [f.note_id for f in references if f.note_id is not None]
    found = {n.id for n in await tickets.role_notes(ids=ids) if n.ticket_number == number}
    for finding in references:
        if finding.prior_id or finding.note_id not in found:
            msg = "a new finding can cite only a review role's note on this ticket"
            raise BadRequestError(msg)


def _fixed_note_ids(rows: list[TicketActivityRow]) -> set[int]:
    by_ticket: dict[int, list[TicketActivityRow]] = defaultdict(list)
    for row in rows:
        by_ticket[row.ticket_number].append(row)
    fixed: set[int] = set()
    for trail in by_ticket.values():
        states, _ = findings_of((row.kind, row.by, row.data) for row in trail)
        ids = {finding.id for finding in states if finding.state == "fixed"}
        fixed.update(
            r.data["note_id"]
            for r in trail
            if r.kind == "finding" and r.data.get("id") in ids and "note_id" in r.data
        )
    return fixed


def number_findings(number: int, review: Review, known: list[str]) -> list[str]:
    """Each finding's id: its `prior_id` when it continues one, else the next `F<n>`."""
    ids: list[str] = []
    next_number = len(known) + 1
    for finding in review.findings:
        if finding.prior_id:
            if finding.prior_id not in known:
                msg = (
                    f"{finding.prior_id} is not a finding of {ticket_id(number)}; leave prior_id "
                    "empty for a new finding"
                )
                raise BadRequestError(msg)
            if finding.prior_id in ids:
                msg = f"{finding.prior_id} is named twice in one review: name it once"
                raise BadRequestError(msg)
            ids.append(finding.prior_id)
        else:
            ids.append(f"F{next_number}")
            next_number += 1
    return ids


class ReviewService:
    """Take a reviewer's verdict and findings."""

    def __init__(self, uow: UnitOfWork, clock: Callable[[], datetime] = utc_now) -> None:
        self._uow = uow
        self._clock = clock

    async def role_note_outcomes(self, since: float, until: float) -> dict[str, tuple[int, int]]:
        """Each role's notes in the range and how many have a linked finding marked fixed."""
        async with self._uow() as session:
            repo = TicketRepository(session)
            notes = await repo.role_notes(
                since=datetime.fromtimestamp(since, UTC), until=datetime.fromtimestamp(until, UTC)
            )
            if not notes:
                return {}
            trail = await repo.finding_trails(sorted({note.ticket_number for note in notes}))
        fixed = _fixed_note_ids(trail)
        count = Counter(str(note.data["review_role"]) for note in notes)
        used = Counter(str(note.data["review_role"]) for note in notes if note.id in fixed)
        return {role: (total, used[role]) for role, total in sorted(count.items())}

    async def submit_review(self, ticket: str, review: Review, *, by: str) -> ReviewSubmitted:
        """Write the review document (a new version each time) and the finding records.

        A new finding is a `finding` record numbered after the ticket's earlier ones; one that
        continues an earlier finding (`prior_id`) is a `finding.kept` record. The submission is
        a `review_submitted` record with the verdict.
        """
        check_review(review)
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number, for_update=True) is None:
                raise not_found(number)
            await _validate_notes(tickets, number, review)
            trail = await tickets.finding_trail(number)
            before = findings_of((r.kind, r.by, r.data) for r in trail)[0]
            ids = number_findings(number, review, [f.id for f in before])
            now = self._clock()
            await _write_findings(tickets, (number, now, by), review, (ids, before))
            store = DocumentRepository(session)
            name = DocumentName.REVIEW.value
            row = await store.find(number, name) or TicketDocumentRow(
                ticket_number=number, name=name, version=0
            )
            last = max(
                (r.data["version"] for r in trail if r.kind == "review_submitted"), default=0
            )
            row.body, row.version = render_review(review, ids), max(row.version, last) + 1
            row.updated_by, row.updated_at = by, now
            await store.save(row)
            submitted = {"verdict": review.verdict, "version": row.version}
            await tickets.append_activity(number, (now, "review_submitted", by), submitted)
        found = [
            FindingId(id=i, severity=f.severity) for f, i in zip(review.findings, ids, strict=True)
        ]
        return ReviewSubmitted(review_version=row.version, findings=found)

    async def dismiss_finding(
        self, ticket: str, finding_id: str, reason: str, *, by: str
    ) -> FindingDismissed:
        """Record that `by` dismissed a finding of the ticket, with its reason.

        The reviewer and the owner read it as a `finding.dismissed` record. A finding the ticket
        does not have, or one already dismissed, is refused.
        """
        why = check_reason(reason)
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number, for_update=True) is None:
                raise not_found(number)
            found = {f.id: f for f in await _standing(tickets, number)}
            if finding_id not in found:
                msg = (
                    f"{finding_id} is not a finding of {ticket_id(number)}; "
                    "the ticket's activity lists its findings"
                )
                raise BadRequestError(msg)
            if found[finding_id].state != "open":
                raise _not_open(found[finding_id])
            record = {"id": finding_id, "reason": why}
            await tickets.append_activity(number, (self._clock(), "finding.dismissed", by), record)
        return FindingDismissed(id=finding_id, reason=why)

    async def list_findings(self, ticket: str) -> list[FindingState]:
        """Every finding of the ticket and where it stands: blocking ones first, then nits."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number) is None:
                raise not_found(number)
            return listing_order(await _standing(tickets, number))

    async def blocking_findings(self, ticket: str) -> list[FindingState]:
        """The ticket's open findings that send a review back."""
        return blocking(await self.list_findings(ticket))

    async def review_findings(self, ticket: str, version: int) -> list[FindingState]:
        """The findings the review of document `version` raised or kept, as they stand now.

        Empty for a version that was not submitted.
        """
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number) is None:
                raise not_found(number)
            trail = await tickets.finding_trail(number)
        found, listed = findings_of((row.kind, row.by, row.data) for row in trail)
        wanted = listed.get(version, [])
        return [f for f in found if f.id in wanted]

    async def latest_review(self, ticket: str) -> ReviewRecord | None:
        """The ticket's latest submitted review; `None` before the first."""
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number) is None:
                raise not_found(number)
            rows = await tickets.finding_trail(number)
        submitted = [row for row in rows if row.kind == "review_submitted"]
        if not submitted:
            return None
        last = submitted[-1]
        return ReviewRecord(
            version=last.data["version"], verdict=last.data["verdict"], at=last.at, by=last.by
        )

    async def close_finding(
        self, ticket: str, finding_id: str, state: str, reason: str, *, by: str
    ) -> FindingState:
        """Close an open finding as `fixed` or `dismissed` with a reason, as the owner does.

        Refused without a reason (`BadRequestError`), for another state, for a finding the ticket
        lacks (`NotFoundError`) and for one closed already (`ConflictError`).
        """
        why = reason.strip()
        if not why:
            raise BadRequestError("a closed finding needs a reason: say why it is closed")
        if state not in CLOSED_STATES:
            raise BadRequestError("a finding closes as fixed or dismissed")
        number = ticket_number(ticket)
        async with self._uow() as session:
            tickets = TicketRepository(session)
            if await tickets.find(number, for_update=True) is None:
                raise not_found(number)
            found = {f.id: f for f in await _standing(tickets, number)}
            if finding_id not in found:
                raise NotFoundError(f"no finding {finding_id} on {ticket_id(number)}")
            if found[finding_id].state != "open":
                raise _not_open(found[finding_id])
            record = {"id": finding_id, "state": state, "reason": why}
            await tickets.append_activity(number, (self._clock(), "finding.closed", by), record)
            return found[finding_id].model_copy(update={"state": state, "reason": why, "by": by})
