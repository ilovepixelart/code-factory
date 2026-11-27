"""An opt-in Build and configured check using each installed, signed-in CLI."""

import asyncio
import socket
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
import uvicorn
from anyio.to_thread import run_sync

from code_factory.agents.models import AgentChange, ConnectionChange
from code_factory.agents.service import AgentService
from code_factory.app import create_app
from code_factory.checks.service import CheckService
from code_factory.platform.config import Settings
from code_factory.platform.served import Served
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.runs.models import StartOptions
from code_factory.runs.service import RunService
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService
from git_support import commit, git

CONFIG = """[agents]
sandbox = true
[checks]
command = \"\"\"python3 -B -c 'import runtime_probe; assert runtime_probe.answer() == 42'\"\"\"
"""
PROMPT = (
    "This is a disposable fixture. Create runtime_probe.py with a function answer() "
    "that returns the integer 42. Commit only that file. Do not use the network."
)


def _repository(root: Path) -> Path:
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    commit(root, "Start fixture", **{".code-factory/config.toml": CONFIG})
    return root


@pytest.fixture
async def live_board(
    settings: Settings,
    migrated: None,  # noqa: ARG001  # isolated worker schema
    tmp_path: Path,
) -> AsyncIterator[tuple[Services, str]]:
    isolated = settings.model_copy(update={
        "state_dir": tmp_path / "state",
        "run_dir": tmp_path / "run",
        "releases_dir": tmp_path / "releases",
    })  # fmt: skip
    root = await run_sync(_repository, tmp_path / "runtime-fixture")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        served = Served("127.0.0.1", port, False, f"http://127.0.0.1:{port}")
        app = create_app(isolated, served=served)
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if task.done():
                        await task
                        pytest.fail("the live test board stopped before serving")
                    await asyncio.sleep(0.05)
            services = cast("Services", app.state.services)
            repository = await services.get(RepositoryService).track(root)
            yield services, repository.name
        finally:
            server.should_exit = True
            await task


async def _run(services: Services, repository: str, runtime: str) -> None:
    ticket = await services.get(TicketService).create(
        NewTicket(repository=repository, title=f"{runtime} runtime trial", labels=[runtime]),
        by="owner",
    )
    runs = services.get(RunService)
    (started,) = (
        await runs.start(ticket.id, stage="build", options=StartOptions(prompt=PROMPT))
    ).runs
    try:
        async with asyncio.timeout(95):
            while (run := await runs.get(started.id)).settled_at is None:  # noqa: ASYNC110
                await asyncio.sleep(0.3)
    except TimeoutError:
        await runs.stop(started.id)
        pytest.fail(f"{runtime} > settlement: timed out")
    assert (run.exit_code, len(run.commits or [])) == (0, 1), f"{runtime} > committed Build"
    assert run.commits is not None
    checks = services.get(CheckService)
    head = run.commits[0]
    async with asyncio.timeout(25):
        while (verdict := await checks.verdict(repository, ticket.id, head)) == "missing":  # noqa: ASYNC110
            await asyncio.sleep(0.3)
    assert verdict == "passed", f"{runtime} > configured check"


@pytest.mark.timeout(240)
async def test_both_local_runtimes_pass_the_configured_check(
    live_board: tuple[Services, str],
) -> None:
    services, repository = live_board
    agents = services.get(AgentService)
    await agents.add_connection(ConnectionChange(name="chatgpt", kind="codex-login"))
    status = (await agents.connection_status()).connections[0]
    assert status.answers, status.problem
    assert status.models, "the Codex login returned no runnable models"
    for runtime, model, connection in (
        ("claude", "sonnet", ""),
        ("codex", status.models[0].id, "chatgpt"),
    ):
        await agents.add_agent(AgentChange(
            name=runtime, runtime=runtime, model=model, connection=connection,
            roles=["build"], labels=[runtime], max_seconds=85,
        ))  # fmt: skip
        await _run(services, repository, runtime)
