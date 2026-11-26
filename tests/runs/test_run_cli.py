"""`code-factory halt`, `resume`, `runs` and the hidden `run-agent`."""

import argparse
import asyncio
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.errors import BadRequestError, NotFoundError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.runs.cli import halt_command, resume_command, runs_command
from code_factory.runs.repository import RunRepository
from code_factory.runs.service import RunService
from code_factory.tickets.models import Ticket
from runs_values import a_run


def parse(command: Command, *argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=command.name)
    command.configure(parser)
    return parser.parse_args(argv)


async def invoke(runs: RunService, command: Command, *argv: str) -> int:
    services = Services()
    services.add(RunService, runs)
    assert command.run_async is not None
    return await command.run_async(parse(command, *argv), services)


async def test_halt_with_nothing_running_holds_the_agents_and_says_so(
    runs: RunService, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await invoke(runs, halt_command) == 0
    assert capsys.readouterr().out == "stopped 0 agents; agents are held until resumed\n"
    assert await runs.halted_at() is not None


async def test_resume_lets_agents_start_again_and_is_idempotent(
    runs: RunService, capsys: pytest.CaptureFixture[str]
) -> None:
    await invoke(runs, halt_command)
    capsys.readouterr()
    assert await invoke(runs, resume_command) == 0
    assert await invoke(runs, resume_command) == 0
    assert capsys.readouterr().out == "agents may start again\nagents may start again\n"
    assert await runs.halted_at() is None


async def test_runs_list_of_a_ticket_shows_its_runs_newest_first(
    runs: RunService, db_session: AsyncSession, ticket: Ticket, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = RunRepository(db_session)
    await repo.insert(a_run(ticket.number, "aaaaaaaaaaaa", agent="writer", exit_code=0))
    await repo.insert(
        a_run(ticket.number, "bbbbbbbbbbbb", started_at=a_run(1).started_at.replace(hour=13))
    )
    assert await invoke(runs, runs_command, "list", "--ticket", ticket.id) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["RUN", "TICKET", "STAGE", "AGENT", "STATE", "STARTED"]
    assert [line.split()[0] for line in lines[1:]] == ["bbbbbbbbbbbb", "aaaaaaaaaaaa"]
    assert lines[2].split()[4] == "finished"
    assert lines[1].split()[4] == "running"


async def test_runs_list_active_shows_only_the_runs_with_no_exit(
    runs: RunService, db_session: AsyncSession, ticket: Ticket, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = RunRepository(db_session)
    await repo.insert(a_run(ticket.number, "aaaaaaaaaaaa", exit_code=0))
    await repo.insert(a_run(ticket.number, "bbbbbbbbbbbb", attempt=1))
    assert await invoke(runs, runs_command, "list", "--active") == 0
    out = capsys.readouterr().out
    assert "bbbbbbbbbbbb" in out
    assert "aaaaaaaaaaaa" not in out


async def test_runs_stop_of_an_unknown_run_says_so(runs: RunService) -> None:
    with pytest.raises(NotFoundError, match="no such run"):
        await invoke(runs, runs_command, "stop", "ffffffffffff")


async def test_runs_stop_needs_a_run_id(runs: RunService) -> None:
    with pytest.raises(BadRequestError, match="stop needs a run id"):
        await invoke(runs, runs_command, "stop")


async def test_run_agent_records_the_agents_exit_and_returns_it(tmp_path: Path) -> None:
    exit_file = tmp_path / "ab12cd34ef56.exit"
    process = await asyncio.create_subprocess_exec(
        str(Path(sys.executable).parent / "code-factory"),
        "run-agent",
        str(exit_file),
        "--",
        "sh",
        "-c",
        "exit 3",
        env={"PATH": "/usr/bin:/bin"},
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert await asyncio.wait_for(process.wait(), 60) == 3
    assert exit_file.read_text().strip() == "3"
