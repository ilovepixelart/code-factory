"""The repository option applies to every part of the production times report."""

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI

from code_factory.checks.models import Judged
from code_factory.checks.rules import checks_record
from code_factory.metrics.cli import metrics_command
from code_factory.metrics.service import MetricsService
from code_factory.repositories.service import RepositoryService
from code_factory.stages.rules import read_log
from code_factory.tickets.models import NewActivity, NewTicket
from code_factory.tickets.service import ActivityService, TicketService

START = datetime(2026, 11, 27, 12, tzinfo=UTC)
TARGET = Judged(head="a" * 40, tree="ticket/sample", tree_id="b" * 40)


async def test_times_repository_selects_its_own_timings_before_limiting(
    app: FastAPI,
    tickets: TicketService,
    activity: ActivityService,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    services = app.state.services
    repositories = services.get(RepositoryService)
    for name in ("earlier", "newer", "empty"):
        await repositories.track(tmp_path / name)
    for name, at, log in (
        ("earlier", START, "gate: pytest passed in 12s\n"),
        ("newer", START + timedelta(hours=1), "gate: web-test passed in 44s\n"),
    ):
        ticket = await tickets.create(NewTicket(repository=name, title="Run checks"), by="owner")
        data = checks_record(TARGET, 0, "checks.log", read_log(log), text=log)
        await activity.append(ticket.id, NewActivity(kind="checks", at=at, data=data), by="owner")

    parser = argparse.ArgumentParser()
    metrics_command.configure(parser)
    assert metrics_command.run_async is not None
    scoped = parser.parse_args(["times", "--last", "1", "--repository", "earlier"])
    assert await metrics_command.run_async(scoped, services) == 0
    output = capsys.readouterr().out
    assert "pytest" in output
    assert "web-test" not in output

    metrics = services.get(MetricsService)
    report = await metrics.times_report(1, "earlier")
    assert report.since == START.timestamp()
    assert [(row.step, row.median) for row in report.steps] == [("pytest", 12)]

    all_repositories = await metrics.times_report(1)
    assert [(row.step, row.median) for row in all_repositories.steps] == [("web-test", 44)]
    empty = await metrics.times_report(1, "empty")
    assert not empty.steps
    assert empty.since is None
