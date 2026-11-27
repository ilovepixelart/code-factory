"""The five `/api/factory` routes: the spec's JSON examples, the errors and the null providers."""

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from code_factory.factory.models import ImprovementPR, Improvements, PullState, ScorerCards
from code_factory.factory.service import FactoryPorts, FactoryService
from factory_fakes import (
    FakeCosts,
    FakeImprovements,
    FakeOwnerTime,
    FakePulls,
    FakeRuns,
    FakeScorers,
)
from factory_values import CARD, COSTS, NOW, OPENED_R1, P0, P2, RUNS
from repo_files import ROOT

RANGE = "from=2026-11-01&to=2026-11-08"


def golden(name: str) -> Any:  # noqa: ANN401
    return json.loads(
        (ROOT / "tests" / "support" / "golden" / "factory" / f"{name}.golden.json").read_text()
    )


@pytest.fixture
async def fed(offline_app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    """A client of the app whose factory reads fixture F1 from in-memory providers."""
    scorers = FakeScorers().holding(ScorerCards(available=True, cards=[CARD]))
    improvements = FakeImprovements().holding(
        Improvements(
            available=True,
            items=[
                ImprovementPR(
                    url="https://github.com/sample/sample/pull/21",
                    number=21,
                    title="Self-improvement: 25 failures",
                    state=PullState.OPEN,
                    opened_at=1794000000.0,
                    failures=25,
                )
            ],
        )
    )
    ports = FactoryPorts(
        FakeRuns().holding(RUNS),
        FakePulls().holding([P0, *OPENED_R1]),
        FakeCosts().holding(COSTS),
        scorers,
        improvements,
        owner_time=FakeOwnerTime(),
    )
    offline_app.state.services.add(FactoryService, FactoryService(ports, now=lambda: NOW))
    transport = httpx.ASGITransport(app=offline_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        yield client


async def test_the_dashboard_answers_the_golden_with_scorers_and_improvements_as_fed(
    fed: httpx.AsyncClient,
) -> None:
    response = await fed.get(f"/api/factory/dashboard?{RANGE}")
    expected = {**golden("dashboard"), "improvements": golden("improvements")}
    assert (response.status_code, response.json()) == (200, expected)


async def test_the_runs_route_answers_the_runs_object_of_the_golden(fed: httpx.AsyncClient) -> None:
    response = await fed.get(f"/api/factory/runs?{RANGE}")
    assert (response.status_code, response.json()) == (200, golden("dashboard")["runs"])


async def test_the_expensive_route_answers_the_spec_example(fed: httpx.AsyncClient) -> None:
    response = await fed.get(f"/api/factory/prs/expensive?{RANGE}&limit=3")
    assert (response.status_code, response.json()) == (200, golden("expensive"))


async def test_the_scorers_route_answers_the_spec_example(fed: httpx.AsyncClient) -> None:
    response = await fed.get(f"/api/factory/scorers?{RANGE}")
    assert (response.status_code, response.json()) == (200, golden("scorers"))


async def test_recording_owner_time_updates_the_merged_pr_cost(fed: httpx.AsyncClient) -> None:
    path = "/api/factory/tickets/CF-2/owner-time"
    entry = {"pull_url": P2.url, "active_minutes": 0, "hourly_rate_usd": 120.0}
    response = await fed.put(path, json=entry)
    assert (response.status_code, response.json()) == (200, entry)
    other = await fed.put("/api/factory/tickets/CF-3/owner-time", json=entry)
    assert (other.status_code, other.json()["detail"]) == (
        404,
        "This ticket has no merged pull request with that URL.",
    )
    dashboard = (await fed.get(f"/api/factory/dashboard?{RANGE}")).json()
    assert dashboard["merged_cost"] == {
        "median": 5.0,
        "priced": 1,
        "owner_recorded": 1,
        "merged": 3,
        "estimated": False,
    }
    for invalid_entry in (
        {"active_minutes": -1},
        {"active_minutes": True},
        {"hourly_rate_usd": 1e100},
    ):
        invalid = await fed.put(path, json={**entry, **invalid_entry})
        assert invalid.status_code == 400


async def test_the_improvements_route_answers_the_spec_example(fed: httpx.AsyncClient) -> None:
    response = await fed.get("/api/factory/improvements?limit=3")
    assert (response.status_code, response.json()) == (200, golden("improvements"))


@pytest.mark.parametrize(
    ("path", "sentence"),
    [
        ("/api/factory/dashboard?from=2026-11-08&to=2026-11-01", "from must be before to"),
        ("/api/factory/runs?from=2026-11-08&to=2026-11-01", "from must be before to"),
        ("/api/factory/scorers?from=2026-11-08&to=2026-11-01", "from must be before to"),
        ("/api/factory/dashboard?from=2024-01-01&to=2026-01-01", "a range is at most 366 days"),
        ("/api/factory/dashboard?from=yesterday", "from is not a date or a time"),
        ("/api/factory/dashboard?to=", "to is not a date or a time"),
        (
            f"/api/factory/prs/expensive?{RANGE}&limit=0",
            "limit must be a whole number from 1 to 50",
        ),
        ("/api/factory/improvements?limit=51", "limit must be a whole number from 1 to 50"),
    ],
)
async def test_a_bad_request_is_a_400_with_the_one_sentence(
    fed: httpx.AsyncClient, path: str, sentence: str
) -> None:
    response = await fed.get(path)
    assert (response.status_code, response.json()["detail"]) == (400, sentence)


async def test_a_provider_that_cannot_answer_is_a_503_with_its_sentence(
    offline_app: FastAPI,
) -> None:
    pulls = FakePulls().holding([])
    pulls.refuses = "the delivery module cannot be reached"
    ports = FactoryPorts(
        FakeRuns().holding([]),
        pulls,
        FakeCosts().holding({}),
        FakeScorers().holding(ScorerCards(available=False)),
        FakeImprovements().holding(Improvements(available=False)),
    )
    offline_app.state.services.add(FactoryService, FactoryService(ports))
    transport = httpx.ASGITransport(app=offline_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get(f"/api/factory/dashboard?{RANGE}")
    assert (response.status_code, response.json()["detail"]) == (
        503,
        "the delivery module cannot be reached",
    )


async def test_an_empty_board_answers_an_empty_dashboard_not_an_error(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(f"/api/factory/dashboard?{RANGE}")
    body: dict[str, Any] = response.json()
    assert response.status_code == 200
    assert body["runs"]["total"] == 0
    assert body["prs"] == {"opened": 0, "merged": 0, "merged_in_period": 0, "open": 0, "closed": 0}
    assert body["autonomy"] == {"share": None, "autonomous": 0, "assisted": 0, "unknown": 0}
    assert body["cost"]["median"] is None
    assert body["merged_cost"] == {
        "median": None,
        "priced": 0,
        "owner_recorded": 0,
        "merged": 0,
        "estimated": False,
    }
    assert body["expensive"] == []
    assert body["scorers"] == {"available": True, "cards": []}
    assert body["improvements"] == {"available": False, "items": []}


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/factory/prs/expensive", {"prs": []}),
        ("/api/factory/scorers", {"available": True, "cards": []}),
        ("/api/factory/improvements", {"available": False, "items": []}),
    ],
)
async def test_an_empty_board_answers_the_other_routes_empty_with_the_default_range(
    client: httpx.AsyncClient, path: str, body: dict[str, Any]
) -> None:
    response = await client.get(path)
    assert (response.status_code, response.json()) == (200, body)
