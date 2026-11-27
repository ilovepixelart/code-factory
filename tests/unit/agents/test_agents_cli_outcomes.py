"""The `agents` command's output for a passed and a failed model check, and a keyless connection."""

import argparse
from datetime import UTC, datetime
from typing import cast

import pytest

from code_factory.agents.cli import agents_command, connections_command
from code_factory.agents.models.agents import AgentDefinition
from code_factory.agents.models.answers import AgentList, ConnectionList, ConnectionView
from code_factory.agents.models.checks import ModelCheck
from code_factory.agents.models.connections import ConnectionDefinition
from code_factory.agents.service import AgentService
from code_factory.platform.module import Command
from code_factory.platform.services import Services

AT = datetime(2026, 1, 1, tzinfo=UTC)


def _check(*, passed: bool, problem: str = "") -> ModelCheck:
    return ModelCheck(
        runtime="claude", connection="", model="m-1", passed=passed, problem=problem, at=AT
    )


class StubAgents:
    def __init__(self, check: ModelCheck) -> None:
        self.check = check

    async def check_model(self, _name: str) -> ModelCheck:
        return self.check

    async def list_definitions(self) -> AgentList:
        return AgentList(
            agents=[
                AgentDefinition(name="a-pass", runtime="claude"),
                AgentDefinition(name="a-fail", runtime="claude"),
            ],
            runtimes=(),
            gaps={},
            roles=(),
            checks={
                "a-pass": _check(passed=True),
                "a-fail": _check(passed=False, problem="no answer"),
            },
        )

    async def list_connections(self) -> ConnectionList:
        keyless = ConnectionDefinition(name="local", kind="ollama", base_url="http://h:1")
        return ConnectionList(
            connections=[ConnectionView(connection=keyless, key_set=False, here=True)],
            kinds=(),
        )


async def run(command: Command, check: ModelCheck, **fields: object) -> int:
    services = Services()
    services.add(AgentService, cast("AgentService", StubAgents(check)))
    assert command.run_async is not None
    return await command.run_async(argparse.Namespace(**{"name": None, **fields}), services)


async def test_a_passed_check_names_the_model_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert await run(agents_command, _check(passed=True), action="check", name="w") == 0
    assert capsys.readouterr().out == "w: m-1 passed its model check\n"


async def test_a_failed_check_prints_its_problem_and_exits_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = await run(
        agents_command, _check(passed=False, problem="no answer"), action="check", name="w"
    )
    assert code == 1
    assert capsys.readouterr().out == "w: no answer\n"


async def test_the_table_shows_each_agents_check_as_passed_or_its_problem(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert await run(agents_command, _check(passed=True), action="list") == 0
    rows = capsys.readouterr().out.splitlines()[1:]
    assert [row.split()[-1] for row in rows] == ["passed", "answer"]
    assert rows[1].endswith("no answer")


async def test_a_connection_without_a_key_variable_shows_a_dash_for_its_key(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert await run(connections_command, _check(passed=True), action="list") == 0
    assert capsys.readouterr().out.splitlines()[1].split() == ["local", "ollama", "http://h:1", "-"]
