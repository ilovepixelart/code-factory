"""The keeper's pass: one repository that cannot be judged never stops the others."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from checks_support import Clock, write_config
from code_factory.checks.models import CheckRun, ReleaseRef
from code_factory.checks.repository import CheckStore
from code_factory.checks.service import CheckService
from code_factory.platform.db import UnitOfWork
from code_factory.repositories.models import RepositoryRecord
from code_factory.repositories.service import RepositoryService
from code_factory.settings.models.errors import ConfigUnjudgedError
from code_factory.tickets.models import Ticket


async def test_a_repository_whose_config_cannot_be_judged_does_not_end_the_pass(
    checks: CheckService, monkeypatch: pytest.MonkeyPatch
) -> None:
    verified: list[str] = []

    async def unjudged(repository: str) -> str | None:
        raise ConfigUnjudgedError(repository)

    async def due_verify(repository: str) -> None:
        verified.append(repository)

    monkeypatch.setattr(checks, "due_main", unjudged)
    monkeypatch.setattr(checks, "due_verify", due_verify)
    await checks.tick()
    assert verified == ["sample"]


async def test_release_verification_waits_for_check_capacity_then_admits_one_repository_at_a_time(
    checks: CheckService,
    repositories: RepositoryService,
    started: Ticket,
    root: Path,
    clock: Clock,
    uow: UnitOfWork,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_config(root, "[checks]\ncommand = 'true'\n")
    check_id = await checks.start(started.id)
    started_checks: asyncio.Queue[int] = asyncio.Queue()
    finish_check: asyncio.Queue[None] = asyncio.Queue()
    started_releases: asyncio.Queue[str] = asyncio.Queue()
    finish_release: asyncio.Queue[None] = asyncio.Queue()
    finished_releases: list[str] = []

    async def hold(row: CheckRun) -> None:
        started_checks.put_nowait(row.id)
        await finish_check.get()
        async with uow() as session:
            await CheckStore(session).runs.lose(row.id, clock.now)

    async def tracked() -> list[RepositoryRecord]:
        return [RepositoryRecord(name=name, path=str(root)) for name in ("sample", "second")]

    async def no_main(_repository: str) -> None:
        return None

    async def due(_repository: str) -> ReleaseRef:
        return ReleaseRef(version="0.1.0", at=clock.now)

    async def verify(repository: str, _release: ReleaseRef) -> None:
        started_releases.put_nowait(repository)
        try:
            await finish_release.get()
        finally:
            finished_releases.append(repository)

    monkeypatch.setattr(checks, "_admission_limit", 1)
    monkeypatch.setattr(checks, "_opts", replace(checks._opts, shutdown_s=0))
    monkeypatch.setattr(checks, "_pipeline", hold)
    monkeypatch.setattr(repositories, "list", tracked)
    monkeypatch.setattr(checks, "due_main", no_main)
    monkeypatch.setattr(checks, "due_verify", due)
    monkeypatch.setattr(checks, "verify", verify)
    supervisor = asyncio.create_task(checks.run_supervisor())
    try:
        assert await asyncio.wait_for(started_checks.get(), timeout=3) == check_id
        await checks.tick()
        await asyncio.sleep(0)
        assert started_releases.empty()

        finish_check.put_nowait(None)
        assert await asyncio.wait_for(started_releases.get(), timeout=3) == "sample"
        following = await checks.start(started.id)
        assert started_releases.empty()

        finish_release.put_nowait(None)
        assert await asyncio.wait_for(started_checks.get(), timeout=3) == following
        assert started_releases.empty()
        finish_check.put_nowait(None)
        assert await asyncio.wait_for(started_releases.get(), timeout=3) == "second"

        await checks.drain()
        assert finished_releases == ["sample", "second"]
    finally:
        supervisor.cancel()
        await asyncio.gather(supervisor, return_exceptions=True)
