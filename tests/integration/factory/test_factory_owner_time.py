"""The migrated table keeps the latest input per pull and reads only named tickets."""

import httpx

from code_factory.delivery.models import PullReading
from code_factory.delivery.repository import DeliveryRepository
from code_factory.factory.models import OwnerTime
from code_factory.factory.service import OwnerTimeService
from code_factory.platform.db import UnitOfWork
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import ActivityService, TicketService
from ticket_values import NOW, OWNER

PULLS = "https://github.com/sample/sample/pull"


async def test_owner_time_is_replaced_per_pull_and_read_in_bulk(uow: UnitOfWork) -> None:
    service = OwnerTimeService(uow)
    first = OwnerTime(pull_url=f"{PULLS}/1", active_minutes=15, hourly_rate_usd=100)
    second = OwnerTime(pull_url=f"{PULLS}/2", active_minutes=25, hourly_rate_usd=120)
    corrected = OwnerTime(pull_url=f"{PULLS}/1", active_minutes=0, hourly_rate_usd=125.50)

    assert await service.recorded(["CF-2"]) == {}
    await service.record("CF-2", first)
    await service.record("CF-2", second)
    await service.record("CF-3", first)
    await service.record("CF-2", corrected)
    await service.record("CF-2", corrected)

    assert await service.recorded(["CF-2"]) == {
        ("CF-2", f"{PULLS}/1"): corrected,
        ("CF-2", f"{PULLS}/2"): second,
    }
    assert await service.recorded(["CF-3"]) == {("CF-3", f"{PULLS}/1"): first}


async def test_the_owner_api_records_a_known_merge_without_ticket_activity(
    client: httpx.AsyncClient, uow: UnitOfWork, tickets: TicketService, activity: ActivityService
) -> None:
    ticket = await tickets.create(NewTicket(repository="sample", title="Merged work"), by=OWNER)
    url = f"{PULLS}/1"
    async with uow() as session:
        await DeliveryRepository(session).record_pull(
            ticket.id,
            ticket.repository,
            url,
            PullReading(state="merged", created_on_host=NOW, merged_on_host=NOW),
            NOW,
        )
    path = f"/api/factory/tickets/{ticket.id}/owner-time"
    entry = {"pull_url": url, "active_minutes": 25, "hourly_rate_usd": 120}

    response = await client.put(path, json=entry)

    assert (response.status_code, response.json()) == (200, entry)
    assert await activity.records_of([ticket.id], "owner_time") == {}
    figures = await client.get("/api/factory/dashboard?from=2026-11-23&to=2026-11-24")
    assert figures.status_code == 200
    assert figures.json()["merged_cost"]["owner_recorded"] == 1


async def test_replacing_the_current_pull_preserves_the_earlier_merge(
    client: httpx.AsyncClient, uow: UnitOfWork, tickets: TicketService
) -> None:
    ticket = await tickets.create(NewTicket(repository="sample", title="Two pulls"), by=OWNER)
    first, second = f"{PULLS}/1", f"{PULLS}/2"
    async with uow() as session:
        repo = DeliveryRepository(session)
        await repo.record_pull(
            ticket.id,
            ticket.repository,
            first,
            PullReading(state="merged", created_on_host=NOW, merged_on_host=NOW),
            NOW,
        )
        await repo.record_pull(ticket.id, ticket.repository, second, PullReading(state="open"), NOW)
        assert (await repo.pulls([ticket.id]))[ticket.id].url == second

    entry = {"pull_url": first, "active_minutes": 30, "hourly_rate_usd": 120}
    recorded = await client.put(f"/api/factory/tickets/{ticket.id}/owner-time", json=entry)
    assert recorded.status_code == 200
    figures = await client.get("/api/factory/dashboard?from=2026-11-23&to=2026-11-24")
    assert figures.status_code == 200
    payload = figures.json()
    assert payload["prs"] == {
        "opened": 2,
        "open": 1,
        "closed": 0,
        "merged": 1,
        "merged_in_period": 1,
    }
    assert payload["merged_cost"]["owner_recorded"] == 1
