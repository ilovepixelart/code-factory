"""Fixtures of the broker tests."""

from collections.abc import AsyncGenerator

import httpx
import pytest
from sqlalchemy import text

from broker_harness import Builder, Clock, FakeConnections, FakeControl, FakeUsage, build, listening
from code_factory.broker.service import BrokerService
from code_factory.platform.config import Settings
from code_factory.platform.db import UnitOfWork, create_engine, create_session_factory


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def conns() -> FakeConnections:
    return FakeConnections()


@pytest.fixture
def usage() -> FakeUsage:
    return FakeUsage()


@pytest.fixture
def control() -> FakeControl:
    return FakeControl()


@pytest.fixture
async def real_uow(settings: Settings, migrated: None) -> AsyncGenerator[UnitOfWork]:  # noqa: ARG001
    """Units of work on real connections that commit, for tests where tasks run at once.

    The broker's table is emptied before and after: only broker tests write to it.
    """
    engine = create_engine(settings)

    async def empty() -> None:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM broker_tokens"))

    await empty()
    try:
        yield UnitOfWork(create_session_factory(engine))
    finally:
        await empty()
        await engine.dispose()


@pytest.fixture
async def make(
    real_uow: UnitOfWork, conns: FakeConnections, usage: FakeUsage, clock: Clock
) -> AsyncGenerator[Builder]:
    """Build services over the committing database; every one that listens is stopped."""
    built: list[BrokerService] = []

    def make_one(**limits: float) -> BrokerService:
        service = build(real_uow, conns, usage, clock, **limits)
        built.append(service)
        return service

    yield make_one
    for service in built:
        service.stopping.set()
        await service.aclose()


@pytest.fixture
async def broker(make: Builder, control: FakeControl) -> AsyncGenerator[BrokerService]:
    """A service that listens, with the run control attached."""
    service = make()
    service.attach_run_control(control)
    task = await listening(service)
    yield service
    service.stopping.set()
    await task


@pytest.fixture
async def http() -> AsyncGenerator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=5) as client:
        yield client


@pytest.fixture
def plain_uow(uow: UnitOfWork) -> UnitOfWork:
    """The isolated, rolled back unit of work, for tests that run one thing at a time."""
    return uow
