"""The follower pass over a real database, with fake neighbours; the leader lock over Postgres."""

import asyncio
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from code_factory.follower.models import ActiveRunFact, Card
from code_factory.follower.ports import FollowerPorts
from code_factory.follower.repository import Leader
from code_factory.follower.rules.queue import Rule
from code_factory.follower.service import FollowerService, QueueService
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine
from code_factory.platform.errors import ConflictError
from code_factory.runs.models import Repair
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService

NOW = datetime(2026, 9, 21, 10, tzinfo=UTC)


class Fakes:
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids
        self.started: list[tuple[str, str]] = []
        self.refuse: dict[str, str] = {}
        self.filed: list[Mapping[str, object]] = []
        self.entries: list[Mapping[str, object]] = []
        self.failing: list[Mapping[str, object]] = []
        self.failed_runs: dict[str, int] = {}
        self.run_stage: dict[str, str] = {}

    async def cards(self) -> list[Card]:
        return [
            Card(
                id=i,
                repository="sample",
                stage="build",
                failures=self.failed_runs.get(i, 0),
                last_end=NOW,
                run_stage=self.run_stage.get(i, ""),
            )
            for i in self.ids
        ]

    async def active(self) -> list[ActiveRunFact]:
        return []

    async def slots(self) -> dict[str, int]:
        return {"sample": 1}

    async def overall(self) -> int | None:
        return None

    async def limits(self) -> dict[str, int]:
        return {}

    async def rule(self, ids: list[str]) -> Rule:  # noqa: ARG002
        return lambda _card: ""

    async def collect(self) -> int:
        return 0

    async def keep(self) -> int:
        return 0

    async def observe(self) -> int:
        return 0

    async def start(
        self,
        ticket_id: str,
        stage: str,
        repair: Repair | None = None,  # noqa: ARG002
    ) -> None:
        if ticket_id in self.refuse:
            raise ConflictError(self.refuse[ticket_id])
        self.started.append((ticket_id, stage))

    async def repositories(self) -> list[str]:
        return ["sample"]

    async def recurring(self, repository: str) -> list[Mapping[str, object]]:  # noqa: ARG002
        return self.entries

    async def sources(self, repository: str) -> set[str]:  # noqa: ARG002
        return {str(f["source"]) for f in self.filed}

    async def file(self, repository: str, fields: Mapping[str, object]) -> str:  # noqa: ARG002
        self.filed.append(fields)
        return f"CF-{100 + len(self.filed)}"

    async def scorer_firings(self, repository: str) -> list[Mapping[str, object]]:  # noqa: ARG002
        return []

    async def failures(self, repository: str) -> list[Mapping[str, object]]:  # noqa: ARG002
        return self.failing


@pytest.fixture
async def ids(tickets: TicketService) -> list[str]:
    made = [
        await tickets.create(NewTicket(repository="sample", title=f"T{n}"), by="owner")
        for n in (1, 2)
    ]
    return [t.id for t in made]


@pytest.fixture
def fakes(ids: list[str]) -> Fakes:
    return Fakes(ids)


@pytest.fixture
def follower(uow: UnitOfWork, fakes: Fakes) -> FollowerService:
    ports = FollowerPorts(board=fakes, work=fakes, filing=fakes)
    return FollowerService(uow, ports, QueueService(uow), clock=lambda: NOW)


async def test_the_first_planned_ticket_starts_and_the_rest_wait_on_the_slot(
    follower: FollowerService, fakes: Fakes, uow: UnitOfWork, ids: list[str]
) -> None:
    report = await follower.run_pass(("start_queued",))

    assert report.steps["start_queued"] == "1 started of 2 planned"
    assert fakes.started == [(ids[0], "build")]
    assert await QueueService(uow).plan() == {ids[0]: "", ids[1]: "sample 1 of 1"}


async def test_a_review_role_due_starts_as_its_own_run_stage(
    follower: FollowerService, fakes: Fakes, ids: list[str]
) -> None:
    fakes.run_stage[ids[0]] = "security"

    await follower.run_pass(("start_queued",))

    assert fakes.started == [(ids[0], "security")]


async def test_a_refused_start_becomes_the_tickets_note(
    follower: FollowerService, fakes: Fakes, uow: UnitOfWork, ids: list[str]
) -> None:
    fakes.refuse[ids[0]] = "no agent takes build"

    await follower.run_pass(("start_queued",))

    assert (await QueueService(uow).plan())[ids[0]] == "not started: no agent takes build"


async def test_a_ticket_whose_run_just_failed_waits_and_the_next_one_starts(
    follower: FollowerService, fakes: Fakes, uow: UnitOfWork, ids: list[str]
) -> None:
    fakes.failed_runs[ids[0]] = 1

    await follower.run_pass(("start_queued",))

    assert fakes.started == [(ids[1], "build")]
    plan = await QueueService(uow).plan()
    assert plan[ids[0]] == "tried again at 10:00:10 UTC, after 1 failed run"


async def test_a_ticket_no_longer_queued_leaves_the_plan(
    follower: FollowerService, fakes: Fakes, uow: UnitOfWork, ids: list[str]
) -> None:
    await follower.run_pass(("start_queued",))
    fakes.ids = [ids[1]]

    await follower.run_pass(("start_queued",))

    assert list(await QueueService(uow).plan()) == [ids[1]]


async def test_a_recurring_entry_is_filed_once_per_period(
    follower: FollowerService, fakes: Fakes
) -> None:
    fakes.entries = [{"title": "Rotate keys", "every": "month", "type": "upgrade"}]

    await follower.run_pass(("file_recurring",))
    await follower.run_pass(("file_recurring",))

    assert [f["source"] for f in fakes.filed] == ["recurring:Rotate keys@2026-09"]


async def test_a_breakage_is_filed_once_however_often_it_is_reported(
    follower: FollowerService, fakes: Fakes
) -> None:
    bug = {"title": "r: main fails", "type": "bug", "source": "main:abc"}
    fakes.failing = [bug, bug]

    await follower.run_pass(("file_failures",))
    await follower.run_pass(("file_failures",))

    assert [f["source"] for f in fakes.filed] == ["main:abc"]


async def test_a_failing_step_does_not_stop_the_pass(
    follower: FollowerService, fakes: Fakes
) -> None:
    async def broken() -> int:
        raise ConflictError("stages could not be read")

    fakes.observe = broken

    report = await follower.run_pass(("observe", "file_recurring"))

    assert report.steps == {
        "observe": "failed: stages could not be read",
        "file_recurring": "0 filed",
    }


async def test_the_follower_retries_leadership_after_a_connection_error(
    follower: FollowerService, fakes: Fakes
) -> None:
    attempts = 0

    async def lead() -> bool:
        nonlocal attempts
        attempts += 1
        if attempts == 3:
            raise asyncio.CancelledError
        follower.wake()
        if attempts == 1:
            raise ConnectionError("database unavailable")
        return True

    with pytest.raises(asyncio.CancelledError):
        await follower.run(2.0, lead)

    assert attempts == 3
    assert fakes.started == [(fakes.ids[0], "build")]


async def test_only_one_leader_holds_the_lock_until_it_lets_go(
    settings: Settings,
    migrated: None,  # noqa: ARG001  # the database exists
) -> None:
    engine = create_engine(settings)
    first, second = Leader(engine), Leader(engine)
    try:
        assert await first.lead()
        assert not await second.lead()
        await first.let_go()
        assert await second.lead()
    finally:
        await first.let_go()
        await second.let_go()
        await engine.dispose()


async def test_an_invalidated_leader_reacquires_instead_of_assuming_it_still_leads(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    engine = create_engine(settings)
    first, second = Leader(engine), Leader(engine)
    try:
        assert await first.lead()
        assert first._connection is not None
        await first._connection.invalidate()
        assert await second.lead()
        assert not await first.lead()
        await second.let_go()
        assert await first.lead()
    finally:
        await first.let_go()
        await second.let_go()
        await engine.dispose()


async def test_leaders_of_two_schemas_both_lead(settings: Settings, migrated: None) -> None:  # noqa: ARG001
    here = create_engine(settings)
    other = f"lead_{uuid.uuid4().hex[:10]}"
    async with here.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{other}"'))
    elsewhere = create_engine(settings.model_copy(update={"db_schema": other}))
    first, second = Leader(here), Leader(elsewhere)
    try:
        assert await first.lead()
        assert await second.lead()
    finally:
        await first.let_go()
        await second.let_go()
        await elsewhere.dispose()
        async with here.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{other}"'))
        await here.dispose()
