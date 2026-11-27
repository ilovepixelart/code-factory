"""Replay synthetic CLI outcomes through the same run lifecycle on any revision."""

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from anyio import Path as AsyncPath
from fastapi import FastAPI

from code_factory.agents.adapters.files import CodexLoginFile
from code_factory.agents.models import AgentChange, ConnectionChange
from code_factory.agents.service import AgentService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import CodeFactoryError
from code_factory.platform.served import Served
from code_factory.platform.services import Services
from code_factory.runs.adapters.processes import ProcessRegistry
from code_factory.runs.ports import Agents, TicketFacts
from code_factory.runs.repository import RunRepository
from code_factory.runs.rules.records import state_of
from code_factory.runs.service import RunService
from runs_fakes import Fakes
from runs_values import a_run

CODEX_OUT = '{"type":"turn.completed","usage":{"input_tokens":4,"output_tokens":3}}\n'
CLAUDE_OUT = '{"type":"result","usage":{"input_tokens":4,"output_tokens":3}}\n'


def checkpoint(case: str, step: str, actual: object, expected: object) -> None:
    """Name the first divergence and show only normalized fixture data."""
    assert actual == expected, f"{case} > {step}: expected {expected!r}, observed {actual!r}"


@pytest.fixture
def real_agents(app: FastAPI) -> Agents:
    service = cast("Services", app.state.services).get(RunService)
    return service._ports.agents


@pytest.fixture
async def catalog(app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    services = cast("Services", app.state.services)
    services.add(Served, Served("127.0.0.1", 4000, False, "http://127.0.0.1:4000"))
    agents: AgentService = services.get(AgentService)
    await agents.add_connection(ConnectionChange(name="chatgpt", kind="codex-login"))
    await agents.add_agent(
        AgentChange(name="writer", runtime="codex", connection="chatgpt", model="unavailable")
    )
    (tmp_path / "auth.json").write_text(
        json.dumps({"tokens": {"access_token": "fixture", "account_id": "fixture"}})
    )
    monkeypatch.setattr(agents, "_login", CodexLoginFile(tmp_path))

    async def version() -> str:
        return "0.123.0"

    async def models(_url: str, _headers: dict[str, str]) -> tuple[int, str]:
        return 200, '{"models":[{"slug":"available","visibility":"list"}]}'

    async def guarded_launch(_plan: object) -> None:
        msg = "launcher reached before model refusal"
        raise CodeFactoryError(msg)

    monkeypatch.setattr("code_factory.agents.adapters.probe.codex_version", version, raising=False)
    monkeypatch.setattr(agents._probe, "get", models)
    monkeypatch.setattr(services.get(RunService)._ports.agents, "launch", guarded_launch)


@pytest.mark.usefixtures("catalog")
async def test_replay_unavailable_model_stops_before_checkout(  # noqa: PLR0913  # isolated ports
    *,
    real_agents: Agents,
    uow: UnitOfWork,
    fakes: Fakes,
    facts: TicketFacts,
    tmp_path: Path,
    registry: ProcessRegistry,
) -> None:
    runs = RunService(
        uow, replace(fakes.ports, agents=real_agents), registry, state_dir=tmp_path / "state"
    )
    try:
        await runs.start(facts.id)
    except CodeFactoryError as refusal:
        message = str(refusal)
    else:
        message = "run started"

    case = "unavailable model"
    checkpoint(
        case,
        "model eligibility",
        message,
        ("connection chatgpt: unavailable; choose a model available to this Codex login in Agents"),
    )
    checkpoint(case, "checkout creation", (tmp_path / "tree-0").exists(), False)
    checkpoint(case, "credential issuance", len(fakes.tokens.issued), 0)
    checkpoint(case, "claim release", fakes.teams.ended_with, [None])


@pytest.mark.parametrize(
    ("case", "exit_record", "log", "commits", "expected"),
    [
        pytest.param("zero exit without a patch", 0, CODEX_OUT, [], "failed", id="no-patch"),
        pytest.param("deadline recovered", -256, CLAUDE_OUT, [], "stopped", id="timeout"),
        pytest.param("completion replayed", 0, CODEX_OUT, ["new"], "finished", id="duplicate"),
    ],
)
async def test_replay_settlement_after_restart(  # noqa: PLR0913  # scenario inputs and dependencies
    *,
    case: str,
    exit_record: int,
    log: str,
    commits: list[str],
    expected: str,
    uow: UnitOfWork,
    fakes: Fakes,
    facts: TicketFacts,
    real_agents: Agents,
    tmp_path: Path,
    runs: RunService,
) -> None:
    fakes.trees.heads = ["new" if commits else "base"]
    fakes.trees.new_commits = commits
    fakes.agents.log_usage = real_agents.log_usage
    state = tmp_path / "state"
    run = a_run(
        facts.number, pid=42, head="base", log=str(state / "runs" / "replayed.log"),
        worktree=str(tmp_path / "tree"), branch="ticket/replayed",
    )  # fmt: skip
    async with uow() as session:
        await RunRepository(session).insert(run)
    exit_file = AsyncPath(runs.exit_file_of(run))
    await exit_file.parent.mkdir(parents=True)
    await exit_file.write_text(f"{exit_record}\n")
    await AsyncPath(run.log).write_text(log)

    await runs.collect()
    await runs.collect()

    ended = await runs.get(run.id)
    checkpoint(case, "run outcome", state_of(ended), expected)
    checkpoint(case, "reported tokens", ended.tokens, 7)
    checkpoint(case, "settlement record", ended.settled_at is not None, True)
    end_events = [event[3] for event in fakes.tickets.events if event[1] == "run.ended"]
    checkpoint(case, "activity event count", len(end_events), 1)
    checkpoint(case, "activity exit code", end_events[0]["exit_code"], ended.exit_code)
    reason = {
        "stopped": "the run exceeded its time limit",
        "failed": "Build produced no verifiable committed changes",
    }.get(expected)
    checkpoint(case, "activity reason", end_events[0].get("reason"), reason)
    checkpoint(case, "credential revocation", fakes.calls.log.count("revoke"), 1)
    checkpoint(case, "claim release", fakes.teams.ended_with, [run.id])
    checkpoint(
        case, "checks queued", fakes.flow.calls, ([("build", facts.id, "new")] if commits else [])
    )
