"""A capped run's provider key: made once, held in memory, deleted when the run ends."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from broker_harness import (
    MANAGEMENT_KEY,
    NOW,
    REAL_KEY,
    RUN_KEY,
    Builder,
    Clock,
    FakeConnections,
    FakeControl,
    issue,
    listening,
    serving,
)
from broker_router import Router
from broker_support import StandIn, raw_http, stand_in
from code_factory.broker.repository import BrokerRepository
from code_factory.broker.service import BrokerService
from code_factory.platform.db import UnitOfWork

CAP = Decimal("2.5")


@pytest.fixture
async def router(conns: FakeConnections) -> AsyncGenerator[tuple[Router, StandIn]]:
    handler = Router()
    async with stand_in(handler) as running:
        conns.add("router", "openrouter", running.base_url, key=REAL_KEY, management=MANAGEMENT_KEY)
        yield handler, running


async def ask(
    http: httpx.AsyncClient, service: BrokerService, token: str, path: str = "/v1/chat/completions"
) -> httpx.Response:
    return await http.post(
        f"{service.endpoints().proxy_url}{path}",
        headers={"authorization": f"Bearer {token}"},
        content=b"{}",
    )


async def capped(service: BrokerService, run: str = "r1") -> str:
    return (await issue(service, run, "router", CAP)).token.get_secret_value()


async def row_state(uow: UnitOfWork, run: str = "r1") -> str | None:
    async with uow() as session:
        row = await BrokerRepository(session).by_run(run)
    return None if row is None else row.key_state


async def test_the_first_request_makes_one_key_with_the_cap_as_limit_and_goes_on_with_it(
    broker: BrokerService, router: tuple[Router, StandIn], http: httpx.AsyncClient
) -> None:
    handler, running = router
    token = await capped(broker)
    first = await ask(http, broker, token)
    second = await ask(http, broker, token)
    assert (first.status_code, second.status_code) == (200, 200)
    assert len(handler.created) == 1
    made = handler.created[0]
    assert made["limit"] == 2.5
    assert "r1" in str(made["name"])
    create = next(s for s in running.seen if s.target == "/v1/keys")
    assert create.header("authorization") == [f"Bearer {MANAGEMENT_KEY}"]
    assert len(handler.on_model) == 2
    for seen in handler.on_model:
        assert seen.header("authorization") == [f"Bearer {RUN_KEY}"]
        assert REAL_KEY.encode() not in seen.everything()


async def test_after_the_run_ends_a_sweep_deletes_the_key_with_the_management_key_and_the_row(
    broker: BrokerService,
    router: tuple[Router, StandIn],
    http: httpx.AsyncClient,
    real_uow: UnitOfWork,
) -> None:
    handler, running = router
    await ask(http, broker, await capped(broker))
    await broker.end_run("r1")
    assert await row_state(real_uow) == "made"  # a key stays until the provider confirms
    report = await broker.sweep()
    assert handler.deleted == ["hash-1"]
    delete = next(s for s in running.seen if s.method == "DELETE")
    assert delete.header("authorization") == [f"Bearer {MANAGEMENT_KEY}"]
    assert (report.deleted, report.failed) == (1, 0)
    assert await row_state(real_uow) is None


async def test_ten_first_requests_at_once_make_exactly_one_key(
    broker: BrokerService, router: tuple[Router, StandIn], http: httpx.AsyncClient
) -> None:
    handler, _ = router
    token = await capped(broker)
    answers = await asyncio.gather(*(ask(http, broker, token) for _ in range(10)))
    assert [a.status_code for a in answers] == [200] * 10
    assert len(handler.created) == 1


async def test_one_runs_create_that_never_answers_holds_no_other_run(
    make: Builder, router: tuple[Router, StandIn], http: httpx.AsyncClient
) -> None:
    handler, _ = router
    handler.hang_for = {"hung"}
    service = make(broker_call_timeout_s=0.5)
    task = await listening(service)
    try:
        hung, fine = await capped(service, "hung"), await capped(service, "fine")
        slow = asyncio.create_task(ask(http, service, hung))
        started = asyncio.get_running_loop().time()
        other = await ask(http, service, fine)
        assert other.status_code == 200
        assert asyncio.get_running_loop().time() - started < 0.4
        stuck = await slow
        assert stuck.status_code == 502
        assert len(handler.on_model) == 1  # only the other run's request went on
    finally:
        service.stopping.set()
        await task


async def test_a_refusal_whose_body_holds_a_key_sends_nothing_with_the_connection_key(
    broker: BrokerService,
    router: tuple[Router, StandIn],
    http: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler, running = router
    handler.create_status = 403
    handler.create_body = {"key": "refused-key-secret", "error": "no"}
    answer = await ask(http, broker, await capped(broker))
    assert answer.status_code == 502
    assert b"refused-key-secret" not in answer.content
    assert "refused-key-secret" not in caplog.text
    assert handler.on_model == []
    assert all(REAL_KEY.encode() not in s.everything() for s in running.seen)


async def test_a_key_made_without_an_id_is_refused_for_good_even_after_a_restart(
    make: Builder, router: tuple[Router, StandIn], http: httpx.AsyncClient, real_uow: UnitOfWork
) -> None:
    handler, _ = router
    handler.create_body = {"key": RUN_KEY}
    first = make()
    task = await listening(first)
    token = await capped(first)
    try:
        assert (await ask(http, first, token)).status_code == 502
    finally:
        first.stopping.set()
        await task
    assert await row_state(real_uow) == "refused"
    second = make()
    task = await listening(second)
    try:
        assert (await ask(http, second, token)).status_code == 502
    finally:
        second.stopping.set()
        await task
    assert len(handler.created) == 1
    assert handler.on_model == []


async def test_a_management_key_that_goes_missing_never_falls_back_to_the_connection_key(
    broker: BrokerService,
    router: tuple[Router, StandIn],
    conns: FakeConnections,
    http: httpx.AsyncClient,
) -> None:
    handler, running = router
    token = await capped(broker)
    del conns.keys["ROUTER_MANAGEMENT_API_KEY"]
    answer = await ask(http, broker, token)
    assert answer.status_code == 502
    assert running.seen == []
    assert handler.on_model == []


async def test_a_connection_off_its_rules_sends_nothing_to_the_key_api(
    broker: BrokerService,
    router: tuple[Router, StandIn],
    conns: FakeConnections,
    http: httpx.AsyncClient,
) -> None:
    _, running = router
    token = await capped(broker)
    conns.broken.add("router")
    assert (await ask(http, broker, token)).status_code == 502
    assert running.seen == []


async def test_a_restart_over_a_made_key_makes_no_second_and_the_sweep_deletes_the_old_one(
    make: Builder,
    router: tuple[Router, StandIn],
    http: httpx.AsyncClient,
    real_uow: UnitOfWork,
) -> None:
    handler, _ = router
    first = make()
    task = await listening(first)
    token = await capped(first)
    try:
        assert (await ask(http, first, token)).status_code == 200
    finally:
        first.stopping.set()
        await task
    second = make()
    second.attach_run_control(FakeControl(active=set()))  # the run is no longer active
    task = await listening(second)
    try:
        assert (await ask(http, second, token)).status_code == 502
        assert len(handler.created) == 1
        report = await second.sweep()
    finally:
        second.stopping.set()
        await task
    assert handler.deleted == ["hash-1"]
    assert report.deleted == 1
    assert await row_state(real_uow) is None


async def test_a_delete_that_hangs_gives_up_in_time_keeps_the_row_and_says_why_in_a_fixed_sentence(
    make: Builder, router: tuple[Router, StandIn], http: httpx.AsyncClient
) -> None:
    handler, _ = router
    service = make(broker_call_timeout_s=0.4)
    task = await listening(service)
    try:
        await ask(http, service, await capped(service))
        await service.end_run("r1")
        handler.delete_hangs = True
        started = asyncio.get_running_loop().time()
        report = await service.sweep()
        assert asyncio.get_running_loop().time() - started < 1.5
        info = await service.describe("r1")
    finally:
        service.stopping.set()
        await task
    assert (report.deleted, report.failed) == (0, 1)
    assert info is not None
    assert info.key_delete_error == "the provider did not answer"


async def test_a_delete_answered_500_is_tried_again_by_the_next_sweep_and_404_counts_as_gone(
    broker: BrokerService,
    router: tuple[Router, StandIn],
    http: httpx.AsyncClient,
    clock: Clock,
    control: FakeControl,
) -> None:
    handler, running = router
    control.active = {"r1", "r2"}
    await ask(http, broker, await capped(broker))
    await broker.end_run("r1")
    handler.delete_status = 500
    first = await broker.sweep()
    assert first.failed == 1
    assert len([s for s in running.seen if s.method == "DELETE"]) == 1
    await ask(http, broker, await capped(broker, "r2"))  # other runs' requests do not retry it
    assert len([s for s in running.seen if s.method == "DELETE"]) == 1
    handler.delete_status = 404
    clock.after(minutes=5)
    second = await broker.sweep()
    assert (second.deleted, second.failed) == (1, 0)
    assert (await broker.describe("r1")) is None


async def test_a_key_id_that_cannot_go_in_a_path_is_not_sent_and_the_row_is_kept(
    broker: BrokerService, router: tuple[Router, StandIn], real_uow: UnitOfWork
) -> None:
    handler, running = router
    await issue(broker, "r9", "router", CAP)
    async with real_uow() as session:
        repo = BrokerRepository(session)
        await repo.set_state("r9", ("none",), "making", NOW)
        await repo.set_state("r9", ("making",), "made", NOW, "../keys/x")
        await repo.end("r9", NOW)
    report = await broker.sweep()
    assert (report.deleted, report.failed) == (0, 1)
    assert running.seen == []
    info = await broker.describe("r9")
    assert info is not None
    assert info.key_delete_error == "its key id cannot be sent"
    assert handler.deleted == []


async def test_a_key_whose_id_cannot_be_recorded_is_deleted_at_once_and_the_request_is_502(
    broker: BrokerService,
    router: tuple[Router, StandIn],
    http: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler, _ = router
    real = BrokerRepository.set_state

    async def failing(  # noqa: PLR0913, PLR0917  # the signature it replaces
        self: BrokerRepository,
        run_id: str,
        was: tuple[str, ...],
        now: str,
        at: datetime,
        key_id: str | None = None,
    ) -> bool:
        if now == "made":
            msg = "the database went away"
            raise OSError(msg)
        return await real(self, run_id, was, now, at, key_id)

    monkeypatch.setattr(BrokerRepository, "set_state", failing)
    answer = await ask(http, broker, await capped(broker))
    assert answer.status_code == 502
    assert handler.deleted == ["hash-1"]
    assert handler.on_model == []


async def test_a_create_started_more_than_two_minutes_ago_is_given_up_and_a_younger_one_is_left(
    broker: BrokerService, real_uow: UnitOfWork, control: FakeControl
) -> None:
    control.active = {"old", "young"}
    for run in ("old", "young"):
        await broker.issue_run_token(run, None, None, NOW + timedelta(hours=1))
    async with real_uow() as session:
        repo = BrokerRepository(session)
        await repo.set_state("old", ("none",), "making", NOW - timedelta(minutes=3))
        await repo.set_state("young", ("none",), "making", NOW - timedelta(minutes=1))
    await broker.sweep()
    assert await row_state(real_uow, "old") == "refused"
    assert await row_state(real_uow, "young") == "making"


async def test_a_row_whose_key_is_not_deleted_outlives_its_ended_run_and_its_dead_token(
    broker: BrokerService,
    router: tuple[Router, StandIn],
    http: httpx.AsyncClient,
    real_uow: UnitOfWork,
    clock: Clock,
) -> None:
    handler, _ = router
    await ask(http, broker, await capped(broker))
    await broker.end_run("r1")
    clock.after(hours=3)
    handler.delete_status = 500
    await broker.sweep()
    assert await row_state(real_uow) == "made"
    assert await broker.verify("cfb_" + "A" * 43) is None


async def test_a_second_sweep_while_the_first_is_deleting_a_key_leaves_it_to_the_first(
    make: Builder,
    router: tuple[Router, StandIn],
    http: httpx.AsyncClient,
) -> None:
    handler, _ = router
    handler.delete_delay = 0.4
    one, two = make(), make()
    async with serving(one):
        await ask(http, one, await capped(one))
        await one.end_run("r1")
        first = asyncio.create_task(one.sweep())
        await asyncio.sleep(0.15)  # the first one has claimed the row and its delete is in flight
        second = await two.sweep()
        done = await first
    assert handler.deleted == ["hash-1"]
    assert (done.deleted, second.deleted) == (1, 0)


@pytest.mark.usefixtures("router")
async def test_after_the_run_ends_holding_a_key_its_token_is_dead_and_the_row_says_so(
    broker: BrokerService, http: httpx.AsyncClient
) -> None:
    token = await capped(broker)
    await ask(http, broker, token)
    await broker.end_run("r1")
    assert (await ask(http, broker, token)).status_code == 401
    assert await broker.verify(token) is None
    info = await broker.describe("r1")
    assert info is not None
    assert info.ended


async def test_the_run_key_expires_when_its_token_does(
    broker: BrokerService, router: tuple[Router, StandIn], http: httpx.AsyncClient
) -> None:
    handler, _ = router
    await ask(http, broker, await capped(broker))
    info = await broker.describe("r1")
    assert info is not None
    expected = info.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert handler.created[0]["expires_at"] == expected


@pytest.mark.parametrize(
    ("method", "target"),
    [
        ("GET", "/v1/keys"),
        ("POST", "/v1/keys"),
        ("DELETE", "/v1/keys/hash-1"),
        ("GET", "/v1/keys/"),
    ],
)
async def test_a_capped_run_cannot_reach_the_key_api_through_its_own_key(
    broker: BrokerService, router: tuple[Router, StandIn], method: str, target: str
) -> None:
    handler, running = router
    token = await capped(broker)
    answer = await raw_http(
        int(broker.endpoints().proxy_url.rsplit(":", 1)[1]),
        method,
        target,
        [("authorization", f"Bearer {token}")],
    )
    assert answer.status == 403
    assert running.seen == []
    assert (handler.created, handler.deleted) == ([], [])
