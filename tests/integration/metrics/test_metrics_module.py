"""The module's adapters against the real services, its command line and its registration."""

import argparse
from pathlib import Path

import pytest

from code_factory.metrics.cli import metrics_command
from code_factory.metrics.models import StageMove
from code_factory.metrics.module import RepositoriesAdapter, TicketsAdapter
from code_factory.metrics.service import MetricsService
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService
from git_support import make_repo
from metrics_support import World
from ticket_values import NOW, OWNER


async def test_the_tickets_adapter_renames_the_flow_facts_of_the_ticket_service(
    tickets: TicketService,
) -> None:
    made = await tickets.create(NewTicket(repository="sample", title="Flowing"), by=OWNER)
    child = await tickets.create(
        NewTicket(repository="sample", title="Defect", caused_by=[made.id]), by=OWNER
    )
    await tickets.set_branch(made.id, "ticket/cf-5", by=OWNER)
    adapter = TicketsAdapter(tickets)

    [flow] = await adapter.flow_facts("sample", [made.id])
    [caused] = await adapter.flow_facts("sample", [child.id])
    building = await adapter.flow_facts("sample", None, ["build"])

    assert (flow.id, flow.title, flow.stage, flow.branch, flow.archived) == (
        made.id,
        "Flowing",
        "build",
        "ticket/cf-5",
        False,
    )
    assert flow.moves == [StageMove(at=NOW, to="build")]
    assert (caused.caused_by, caused.stage, caused.needs) == ([made.id], "spec", "")
    assert [f.id for f in building] == [made.id]


async def test_the_repositories_adapter_gives_each_checkout_its_default_branch(
    tmp_path: Path, repositories: RepositoryService
) -> None:
    root = make_repo(tmp_path, "sample", branch="trunk")
    await repositories.track(root)

    class Git:
        async def facts(self, repository: str) -> object:
            assert repository == "sample"
            return type("Facts", (), {"default_branch": "trunk"})()

    adapter = RepositoriesAdapter(repositories, Git())  # ty: ignore[invalid-argument-type]  # a stub of facts
    [found] = await adapter.tracked()
    assert (found.name, found.path) == ("sample", root)
    assert await adapter.default_branch("sample") == "trunk"


async def test_listing_the_tracked_repositories_starts_no_git_process(
    tmp_path: Path, repositories: RepositoryService
) -> None:
    await repositories.track(make_repo(tmp_path, "sample"))
    asked: list[str] = []

    class Git:
        async def facts(self, repository: str) -> object:
            asked.append(repository)
            raise AssertionError(repository)

    adapter = RepositoriesAdapter(repositories, Git())  # ty: ignore[invalid-argument-type]  # a stub of facts
    assert [r.name for r in await adapter.tracked()] == ["sample"]
    assert asked == []


def parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="metrics")
    metrics_command.configure(parser)
    return parser.parse_args(argv)


@pytest.fixture
def services(metrics: MetricsService) -> Services:
    registry = Services()
    registry.add(MetricsService, metrics)
    return registry


async def run(services: Services, *argv: str) -> int:
    run_async = metrics_command.run_async
    assert run_async is not None
    return await run_async(parse(*argv), services)


async def test_times_with_no_recorded_run_says_so_and_exits_zero(
    services: Services, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await run(services, "times") == 0
    assert capsys.readouterr().out == "no gate run has recorded step times yet\n"


async def test_forecast_prints_the_open_count_and_says_when_it_cannot_forecast(
    services: Services, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await run(services, "forecast", "--open", "3") == 0
    assert capsys.readouterr().out == (
        "open: 3\nno ticket reached review in the last 56 days: no forecast\n"
    )
    assert await run(services, "forecast", "--open", "0") == 0
    assert capsys.readouterr().out == "open: 0\ndone in 0 days (50%), 0 days (85%)\n"


async def test_refresh_prints_a_line_per_repository(
    services: Services, capsys: pytest.CaptureFixture[str], world: World
) -> None:
    assert await run(services, "refresh") == 0
    assert (
        capsys.readouterr().out
        == f"{world.repositories.repos[0].name}: 0 merges, 0 new, 0 reverted, 0 branch cuts\n"
    )


async def test_factory_prints_a_header_for_no_work(
    services: Services, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await run(services, "factory") == 0
    assert capsys.readouterr().out.startswith("agent  model  runs")
