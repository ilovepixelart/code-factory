"""Queries over the permission tables."""

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.db import lock_until_commit
from code_factory.runs.models import Decision, PermissionRequest, Review
from code_factory.runs.tables import (
    PermissionDecisionRow,
    PermissionRequestRow,
    PermissionReviewRow,
    PermissionRuleRow,
)

_PENDING = PermissionRequestRow.status == "pending"


def _request(row: PermissionRequestRow) -> PermissionRequest:
    return PermissionRequest.model_validate(row, from_attributes=True)


class PermissionRepository:
    """Permission requests, their decisions, reviews and the owner's standing rules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_request(self, request: PermissionRequest) -> None:
        """Record a request."""
        self._session.add(PermissionRequestRow(**request.model_dump()))
        await self._session.flush()

    async def get_request(self, request_id: str) -> PermissionRequest | None:
        """The request, answered or not."""
        row = await self._session.get(PermissionRequestRow, request_id, populate_existing=True)
        return None if row is None else _request(row)

    async def pending(self) -> list[PermissionRequest]:
        """Requests nobody answered yet, oldest first."""
        rows = await self._session.scalars(
            select(PermissionRequestRow)
            .where(_PENDING)
            .order_by(PermissionRequestRow.requested_at, PermissionRequestRow.id)
        )
        return [_request(row) for row in rows]

    async def answer(self, request_id: str, verdict: str, by: str, at: datetime) -> bool:
        """Record the answer of a pending request; `False` when it is no longer pending."""
        won = await self._session.scalar(
            update(PermissionRequestRow)
            .where(PermissionRequestRow.id == request_id, _PENDING)
            .values(status="answered", verdict=verdict, answered_by=by, answered_at=at)
            .returning(PermissionRequestRow.id)
        )
        return won is not None

    async def withdraw(self, request_id: str) -> bool:
        """End a pending request the agent stopped waiting for; `False` when it is not pending."""
        won = await self._session.scalar(
            update(PermissionRequestRow)
            .where(PermissionRequestRow.id == request_id, _PENDING)
            .values(status="withdrawn")
            .returning(PermissionRequestRow.id)
        )
        return won is not None

    async def withdraw_pending_before(self, moment: datetime) -> int:
        """End the pending requests made before `moment`: their waiters died with the process."""
        rows = await self._session.scalars(
            update(PermissionRequestRow)
            .where(_PENDING, PermissionRequestRow.requested_at < moment)
            .values(status="withdrawn")
            .returning(PermissionRequestRow.id)
        )
        return len(rows.all())

    async def expire_before(self, moment: datetime) -> list[PermissionRequest]:
        """Expire the pending requests made before `moment`; the ones expired."""
        rows = await self._session.scalars(
            update(PermissionRequestRow)
            .where(_PENDING, PermissionRequestRow.requested_at < moment)
            .values(status="expired")
            .returning(PermissionRequestRow)
            .execution_options(populate_existing=True)
        )
        return sorted((_request(row) for row in rows), key=lambda r: (r.requested_at, r.id))

    async def answered_history(self) -> list[tuple[str, bool]]:
        """Each answered request that a standing rule could cover: its kind, and whether allowed."""
        rows = await self._session.execute(
            select(PermissionRequestRow.kind, PermissionRequestRow.verdict).where(
                PermissionRequestRow.status == "answered", PermissionRequestRow.kind.is_not(None)
            )
        )
        return [(str(kind), verdict == "allow") for kind, verdict in rows]

    async def rules(self) -> list[str]:
        """The kinds the owner adopted, in the order adopted."""
        rows = await self._session.scalars(
            select(PermissionRuleRow.kind).order_by(
                PermissionRuleRow.adopted_at, PermissionRuleRow.kind
            )
        )
        return list(rows)

    async def adopt_rule(self, kind: str, at: datetime) -> bool:
        """Adopt a standing rule; `False` when it already is one."""
        added = await self._session.scalar(
            insert(PermissionRuleRow)
            .values(kind=kind, adopted_at=at)
            .on_conflict_do_nothing()
            .returning(PermissionRuleRow.kind)
        )
        return added is not None

    async def add_decision(self, decision: Decision) -> None:
        """Record a decision."""
        self._session.add(PermissionDecisionRow(**decision.model_dump()))
        await self._session.flush()

    async def latest_decisions(
        self, repository: str, ticket_key: str, count: int
    ) -> list[Decision]:
        """The last `count` decisions on the ticket's requests, oldest first."""
        rows = await self._session.scalars(
            select(PermissionDecisionRow)
            .where(
                PermissionDecisionRow.repository == repository,
                PermissionDecisionRow.ticket_key == ticket_key,
            )
            .order_by(PermissionDecisionRow.id.desc())
            .limit(count)
        )
        return [Decision.model_validate(row, from_attributes=True) for row in reversed(rows.all())]

    async def prune_decisions(self, before: datetime) -> int:
        """Delete decisions made before `before`; how many."""
        gone = await self._session.scalars(
            delete(PermissionDecisionRow)
            .where(PermissionDecisionRow.at < before)
            .returning(PermissionDecisionRow.id)
        )
        return len(gone.all())

    async def record_review(self, review: Review) -> int:
        """Record a review and give its session's tally including it.

        The count and the insert run under the session's advisory lock, so two reviews of one
        session never read the same tally.
        """
        await lock_until_commit(self._session, f"permission-review:{review.session_id}")
        self._session.add(PermissionReviewRow(**review.model_dump()))
        await self._session.flush()
        return await self.review_count(review.session_id)

    async def review_count(self, session_id: str) -> int:
        """How many reviews the session has had."""
        count = await self._session.scalar(
            select(func.count())
            .select_from(PermissionReviewRow)
            .where(PermissionReviewRow.session_id == session_id)
        )
        return int(count or 0)

    async def review_verdicts(self, session_id: str) -> list[str]:
        """The verdicts of the session's reviews, oldest first."""
        rows = await self._session.scalars(
            select(PermissionReviewRow.verdict)
            .where(PermissionReviewRow.session_id == session_id)
            .order_by(PermissionReviewRow.id)
        )
        return list(rows)
