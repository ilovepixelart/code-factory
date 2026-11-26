"""Fixtures of the metrics tests: a dated repository `sample`, the fake ports and a service."""

import asyncio
from pathlib import Path

import pytest

from code_factory.metrics.service import MetricsService
from code_factory.platform.db import UnitOfWork
from metrics_support import World, sample_repo


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """The main checkout of repository `sample`, one commit dated twenty days before NOW."""
    return sample_repo(tmp_path)


@pytest.fixture
def world(root: Path) -> World:
    """The four fakes, with `sample` tracked at `root`."""
    world = World()
    world.track(root)
    return world


@pytest.fixture
def metrics(uow: UnitOfWork, world: World) -> MetricsService:
    """The service over the isolated database, the fakes and the real git reader."""
    return world.service(uow)


@pytest.fixture(autouse=True)
def _idle_refresh_loop_outside_metrics_tests(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the lifespan's refresh loop off the one shared test connection.

    Its first pass runs at start and would interleave savepoints with the test's own requests on
    that connection; the metrics tests call the loop themselves, on their own service.
    """
    if "metrics" in request.path.parts:
        return

    async def idle(_self: MetricsService) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(MetricsService, "run_refresh_loop", idle)
