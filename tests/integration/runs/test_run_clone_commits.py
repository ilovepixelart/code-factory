"""A run's commits, read once its clone's branch is back in the main repository: real git."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from code_factory.git.service import GitService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.services import Services
from code_factory.runs.adapters.processes import ProcessRegistry
from code_factory.runs.ports import TicketFacts
from code_factory.runs.service import RunService
from code_factory.runs.service.neighbours import TreesAdapter
from git_support import Fakes as GitFakes
from git_support import git, make_repo, make_service, ticket_ref
from runs_fakes import Fakes
from runs_values import FakeClock

COMMIT = "git -c user.name=t -c user.email=t@example.com commit -q --allow-empty -m 'Run work'"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "git")


@pytest.fixture
def real_runs(  # noqa: PLR0913, PLR0917  # the service's parts, all named
    uow: UnitOfWork,
    fakes: Fakes,
    facts: TicketFacts,
    registry: ProcessRegistry,
    tmp_path: Path,
    clock: FakeClock,
    root: Path,
) -> RunService:
    """The run service with its trees over the real git service; the other ports fake."""
    git_fakes = GitFakes(roots={"sample": root}, tickets={facts.id: ticket_ref(facts.id)})
    services = Services()
    services.add(GitService, make_service(uow, git_fakes))
    ports = replace(fakes.ports, trees=TreesAdapter(services))
    return RunService(uow, ports, registry, state_dir=tmp_path / "state", clock=clock)


async def test_the_commits_a_run_made_in_its_clone_are_recorded(
    real_runs: RunService, fakes: Fakes, facts: TicketFacts, root: Path
) -> None:
    fakes.agents.script = COMMIT
    run = (await real_runs.start(facts.id)).runs[0]
    for _ in range(200):
        if real_runs.exit_path(run.id).exists():
            break
        await asyncio.sleep(0.05)

    await real_runs.collect()

    made = git(Path(run.worktree), "rev-parse", "HEAD")
    assert made != run.head
    assert (await real_runs.get(run.id)).commits == [made]
    assert git(root, "rev-parse", run.branch) == made
