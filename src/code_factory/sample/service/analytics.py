"""Recorded activity to populate the demo's analytics without running agents."""

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta

from code_factory.delivery.models import Ci, PullReading
from code_factory.delivery.service import DeliveryService
from code_factory.factory.models import OwnerTime
from code_factory.factory.service import FactoryService
from code_factory.runs.models import Run
from code_factory.runs.service import RunService
from code_factory.sample.models.demo import DEMO_PULL_SIZES, DEMO_TICKETS, DemoTicket, Stage
from code_factory.sample.rules import pull_url
from code_factory.talk.models import Reply
from code_factory.talk.service import TalkService
from code_factory.tickets.models import NewTicket, Review
from code_factory.tickets.service import ActivityService, ReviewService, TicketService

CLOSED_PULL = "Checkout keeps the address after a failed payment"
IDLE_PULL = "Search ranks in-stock products first"
READY_PULL = "Issue a gift card code on purchase"
OWNER_TIME_DEMO_DAYS = 7


async def record_open_pull(
    delivery: DeliveryService, spec: DemoTicket, ticket: str, head: str, now: datetime
) -> None:
    """Read an open PR as ready, failing, or idle, with the recorded branch head."""
    additions, deletions, changed_files = DEMO_PULL_SIZES.get(spec.title, (202, 74, 5))
    idle = spec.title == IDLE_PULL
    ready = spec.title == READY_PULL
    await delivery.record_reading(
        ticket,
        spec.repository,
        pull_url(spec.repository, ticket),
        PullReading(
            state="open",
            ci=_open_ci(spec, idle=idle),
            head=head,
            base="main",
            additions=additions,
            deletions=deletions,
            changed_files=changed_files,
            created_on_host=now - timedelta(days=5 if idle else 1),
            updated_on_host=now - timedelta(days=3) if idle else now,
        ),
        shipped_head=head if ready else "",
    )


def _runs(
    spec: DemoTicket, ticket: str, started: datetime, *, head: str, failed: bool
) -> list[Run]:
    number = int(ticket.removeprefix("CF-"))
    model = "claude-sonnet-5-5"
    rows = []
    for index, (stage, agent, cost) in enumerate(
        [("spec", "builder", 0.24), ("build", "builder", 1.12), ("review", "reviewer", 0.38)]
    ):
        began = started + timedelta(hours=2 * index)
        ended = began + timedelta(minutes=6 + number)
        rows.append(
            Run(
                id=f"demo-{ticket.lower()}-{stage}",
                ticket_id=number,
                ticket_key=ticket,
                repository=spec.repository,
                branch=f"ticket/{ticket.lower()}",
                stage=stage,
                started_at=began,
                ended_at=ended,
                settled_at=ended,
                exit_code=int(failed and stage == "build"),
                agent=agent,
                model=model if stage != "review" else "claude-opus-5-5",
                cost=round(cost * (1 + (number % 4) / 2), 2),
                cost_estimated=number % 2 == 0,
                tokens=(index + 1) * (4000 + number * 125),
                turns=2 + index,
                tests_checked=stage == "build",
                commits=[head] if stage == "build" and number % 4 else [],
            )
        )
    return rows


def _open_ci(spec: DemoTicket, *, idle: bool) -> Ci:
    if idle:
        return "pending"
    return "failed" if spec.repository == "infra" else "passed"


def _history_reading(
    number: int, merged: datetime | None, opened: datetime, now: datetime
) -> PullReading:
    """A merged PR, or a closed one when `merged` is None."""
    closed = merged is None
    return PullReading(
        state="closed" if closed else "merged",
        ci="failed" if closed else "passed",
        additions=36 + (number % 5) ** 3 * 18,
        deletions=12 + number,
        changed_files=2 + number % 8,
        created_on_host=opened,
        updated_on_host=merged or now,
        merged_on_host=merged,
        first_review_at=opened + timedelta(hours=3 + number % 8),
    )


async def record_pull_history(
    delivery: DeliveryService,
    runs: RunService,
    ids: Mapping[str, str],
    heads: Mapping[str, str],
    now: datetime,
) -> None:
    """Record merged, closed and still-open PR costs on the tickets already in the demo."""
    history: list[Run] = []
    for spec in DEMO_TICKETS:
        ticket = ids[spec.title]
        head = heads.get(spec.title, "")
        closed = spec.title == CLOSED_PULL
        if not closed and (spec.stage is Stage.REVIEW or spec.title == IDLE_PULL):
            history.extend(_runs(spec, ticket, now - timedelta(days=1), head=head, failed=False))
            continue
        if not closed and spec.stage not in {Stage.MERGED, Stage.RELEASED}:
            continue
        merged = None if closed else now - timedelta(days=spec.merged_days_ago)
        opened = (merged or now) - timedelta(days=1)
        number = int(ticket.removeprefix("CF-"))
        await delivery.record_reading(
            ticket,
            spec.repository,
            pull_url(spec.repository, ticket),
            _history_reading(number, merged, opened, now),
        )
        history.extend(_runs(spec, ticket, opened - timedelta(hours=2), head=head, failed=closed))
    await runs.import_completed(history)


async def record_owner_time(factory: FactoryService, ids: Mapping[str, str]) -> None:
    """Seed owner time for recent merges and leave older costs incomplete."""
    for spec in DEMO_TICKETS:
        if (
            spec.stage in {Stage.MERGED, Stage.RELEASED}
            and spec.merged_days_ago <= OWNER_TIME_DEMO_DAYS
        ):
            ticket = ids[spec.title]
            await factory.record_owner_time(
                ticket,
                OwnerTime(
                    pull_url=pull_url(spec.repository, ticket),
                    active_minutes=spec.merged_days_ago + 5,
                    hourly_rate_usd=90,
                ),
            )


async def _record_stage_history(tickets: TicketService, ticket: str, merged: datetime) -> None:
    """Give a historical merge a timeline consistent with its seeded git commits."""
    moves = (("spec", "build", 24), ("build", "review", 8), ("review", "merged", 0))
    for before, after, hours in moves:
        await tickets.record_activity(
            ticket,
            "stage",
            {"from": before, "to": after},
            by="demo",
            at=merged - timedelta(hours=hours),
        )


async def file_tickets(
    tickets_at: Callable[[datetime], TicketService], now: datetime
) -> dict[str, str]:
    """File tickets and their earlier stage moves in the order their links refer to them."""
    ids: dict[str, str] = {}
    for spec in DEMO_TICKETS:
        fields: dict[str, object] = {
            "repository": spec.repository,
            "title": spec.title,
            "type": spec.type,
            "labels": list(spec.labels),
            "priority": spec.priority,
            "description": spec.description,
            "blocked": spec.blocked,
        }
        if spec.parent:
            fields["parent"] = ids[spec.parent]
        if spec.blocked_by:
            fields["blocked_by"] = [ids[title] for title in spec.blocked_by]
        merged = now - timedelta(days=spec.merged_days_ago)
        tickets = tickets_at(merged - timedelta(days=3))
        ticket = await tickets.create(NewTicket.model_validate(fields), by="demo")
        ids[spec.title] = ticket.id
        if spec.stage in {Stage.MERGED, Stage.RELEASED}:
            await _record_stage_history(tickets, ticket.id, merged)
    return ids


async def record_response_history(
    talk_at: Callable[[datetime], TalkService], ids: Mapping[str, str], now: datetime
) -> None:
    """Keep the live questions open and add representative past answer times."""
    examples = (
        ("Gift cards", "Is the first release limited to one currency?", "Yes, use CHF.", 17),
        ("Wishlist shared by link", "Should old links keep working?", "Keep old links active.", 42),
        (CLOSED_PULL, "Can we punt the legacy form?", "Yes, keep its current flow.", 75),
    )
    answered = now - timedelta(days=1)
    for title, question, answer, minutes in examples:
        asked = await talk_at(answered - timedelta(minutes=minutes)).ask(
            ids[title], question, [], by="run:demo-builder"
        )
        await talk_at(answered).answer(
            asked.question_id, Reply(text=answer), by="owner", channel="http"
        )


async def record_review_notes(
    activities: ActivityService, reviews: ReviewService, ticket: str
) -> None:
    """Show review-role notes with an example of a note linked to a completed fix."""
    messages = {
        "qa": "Verify the page still loads images while navigating with the keyboard.",
        "security": "Keep private image URLs out of the preload list.",
        "tests": "Assert that images above the fold load eagerly.",
    }
    notes = {
        role: await activities.record_note(
            ticket, message, "note", by=f"run:demo-{role}", review_role=role
        )
        for role, message in messages.items()
    }
    review = Review.model_validate(
        {
            "verdict": "changes",
            "summary": "Cover keyboard navigation before enabling lazy loading.",
            "findings": [{"severity": "major", "text": messages["qa"], "note_id": notes["qa"].id}],
        }
    )
    submitted = await reviews.submit_review(ticket, review, by="run:demo-review")
    (finding,) = submitted.findings
    await reviews.close_finding(
        ticket, finding.id, "fixed", "Verified keyboard navigation in the storefront.", by="owner"
    )
