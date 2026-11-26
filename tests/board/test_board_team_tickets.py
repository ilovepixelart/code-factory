"""The team's tickets over the real services: each ticket's records, and a merge by its record."""

from datetime import UTC, datetime, timedelta
from typing import cast

from fastapi import FastAPI

from code_factory.delivery.models import DeliveryEvent
from code_factory.delivery.repository import DeliveryRepository
from code_factory.metrics.models import Autonomy, ChecksVerdict, MergeFact
from code_factory.metrics.repository import MetricsRepository
from code_factory.platform.db import UnitOfWork
from code_factory.platform.services import Services
from code_factory.team.models import TicketFacts
from code_factory.team.service import TicketSource
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService

URL = "https://github.com/o/r/pull/3"


def _services(app: FastAPI) -> Services:
    return cast("Services", app.state.services)


async def _facts(app: FastAPI, since: float) -> dict[str, TicketFacts]:
    found = await _services(app).get(TicketSource).team_facts(since)
    return {facts.reference.id: facts for facts in found}


async def _merged(app: FastAPI, uow: UnitOfWork, title: str, at: datetime | None) -> str:
    """A merged ticket; its pull request's merge recorded at `at`, or no merge recorded."""
    tickets = _services(app).get(TicketService)
    made = await tickets.create(NewTicket(repository="sample", title=title), by="o")
    await tickets.set_merged(made.id, True, by="o")
    if at is not None:
        async with uow() as session:
            await DeliveryRepository(session).record(
                DeliveryEvent(ticket_id=made.id, kind="merged_pull_request", url=URL, at=at)
            )
    return made.id


async def test_each_ticket_carries_its_records_with_their_words_oldest_first(
    app: FastAPI, uow: UnitOfWork
) -> None:
    tickets = _services(app).get(TicketService)
    made = await tickets.create(NewTicket(repository="sample", title="Add totals"), by="o")
    await tickets.record_activity(made.id, "checks", {"exit_code": 0, "commit": "abc"}, by="c")
    async with uow() as session:
        await DeliveryRepository(session).record(
            DeliveryEvent(ticket_id=made.id, kind="pull_request", url=URL, at=datetime.now(UTC))
        )

    facts = (await _facts(app, 0))[made.id]

    assert [(a.kind, a.words) for a in facts.activities] == [
        ("created", "Created as a feature"),
        ("checks", "Checks passed"),
        ("pull_request", "Pull request"),
    ]
    assert facts.activities[1].text("exit_code") == "0"
    assert facts.activities[2].text("url") == URL


async def test_a_merge_counts_from_its_recorded_merge_not_from_the_boards_move(
    app: FastAPI, uow: UnitOfWork
) -> None:
    now = datetime.now(UTC)
    today = await _merged(app, uow, "Merged today", now - timedelta(hours=1))
    earlier = await _merged(app, uow, "Merged last week", now - timedelta(days=5))
    unrecorded = await _merged(app, uow, "Merged elsewhere", None)

    facts = await _facts(app, (now - timedelta(days=1)).timestamp())

    assert facts[today].merged == (now - timedelta(hours=1)).timestamp()
    assert earlier not in facts
    assert unrecorded not in facts


async def test_a_ticket_carries_the_checks_verdict_the_card_reads(app: FastAPI) -> None:
    tickets = _services(app).get(TicketService)
    failed = await tickets.create(NewTicket(repository="sample", title="Failed"), by="o")
    killed = await tickets.create(NewTicket(repository="sample", title="Killed"), by="o")
    await tickets.record_activity(failed.id, "checks", {"exit_code": 1, "commit": "abc"}, by="c")
    # A run the system killed says nothing about the code: no verdict, as on the card.
    await tickets.record_activity(killed.id, "checks", {"exit_code": 137, "commit": "abc"}, by="c")

    facts = await _facts(app, 0)

    assert (facts[failed.id].check, facts[killed.id].check) == (False, None)


async def test_a_merge_the_ledger_read_from_git_dates_a_merge_the_board_did_not_make(
    app: FastAPI, uow: UnitOfWork
) -> None:
    now = datetime.now(UTC)
    landed = now - timedelta(hours=2)
    outside = await _merged(app, uow, "Merged on the forge", None)
    async with uow() as session:
        await MetricsRepository(session).upsert_merges(
            [
                MergeFact(
                    repository="sample",
                    commit="c0ffee",
                    head="h",
                    pull=4,
                    branch="ticket/x",
                    ticket=outside,
                    at=landed.timestamp(),
                    started=landed.timestamp(),
                    reverted=False,
                    autonomy=Autonomy.AUTONOMOUS,
                    checks=ChecksVerdict.PASSED,
                )
            ],
            now.timestamp(),
        )

    facts = await _facts(app, (now - timedelta(days=1)).timestamp())

    assert facts[outside].merged == landed.timestamp()


async def test_records_of_other_kinds_are_carried_only_among_the_newest_five(
    app: FastAPI,
) -> None:
    tickets = _services(app).get(TicketService)
    made = await tickets.create(NewTicket(repository="sample", title="Add totals"), by="o")
    for number in range(1, 7):
        await tickets.record_activity(made.id, "note", {"text": f"note {number}"}, by="o")

    facts = (await _facts(app, 0))[made.id]

    assert [a.words for a in facts.activities] == [
        "Created as a feature",
        "note 2",
        "note 3",
        "note 4",
        "note 5",
        "note 6",
    ]
