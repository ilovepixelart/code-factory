"""The command and environment a claude run starts with, built over the app's own services."""

import asyncio
import json
import os
import sys
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest
from anyio import Path as AsyncPath
from fastapi import FastAPI

from code_factory.agents.models import ConnectionChange
from code_factory.agents.service import AgentService
from code_factory.git.service import GitService
from code_factory.platform.errors import UnavailableError
from code_factory.platform.served import Served
from code_factory.runs.models import RunHooks
from code_factory.runs.ports import Given, LaunchPlan, TicketFacts, Tree
from code_factory.runs.service import codex
from code_factory.runs.service.launching import NOT_SERVED, RunLauncher
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService

BOARD = "http://127.0.0.1:4000"
HOOKS = RunHooks(
    permission="ask-hook", tell="tell-hook", recall="recall-hook", rewrite="guard-hook"
)


class Hooks:
    def run_hooks(self) -> RunHooks:
        return HOOKS


async def _plan(app: FastAPI, tmp_path: Path, runtime: str = "claude") -> LaunchPlan:
    ticket = await app.state.services.get(TicketService).create(
        NewTicket(repository="sample", title="Paint the fence"), by="owner"
    )
    return LaunchPlan(
        run_id="ab12cd34ef56",  # a run id as the board makes one: 12 hex digits
        stage="build",
        ticket=TicketFacts(
            id=ticket.id, number=1, repository="sample", title=ticket.title, kind="feature"
        ),
        tree=Tree(name="t", path=tmp_path, branch="ticket/cf-1"),
        given=Given(agent="", runtime=runtime, model="", connection="", fingerprint="f"),
        permissions="acceptEdits",
        remaining=None,
        exit_file=tmp_path / "ab12cd34ef56.exit",
        log=tmp_path / "ab12cd34ef56.log",
        token="run-token",  # noqa: S106  # a stand-in the test looks for
    )


def _launcher(app: FastAPI, *, base_url: str = BOARD) -> RunLauncher:
    services = app.state.services
    services.add(
        Served, Served(address="127.0.0.1", port=4000, both_loopbacks=False, base_url=base_url)
    )
    return RunLauncher(services, app.state.settings, Hooks())


def _after(argv: tuple[str, ...], flag: str) -> str:
    return argv[argv.index(flag) + 1]


async def test_a_claude_run_starts_in_the_wrapper_with_its_sandbox_hooks_and_board_mcp(
    app: FastAPI, tmp_path: Path
) -> None:
    plan = await _plan(app, tmp_path)

    launch = await _launcher(app).launch(plan)

    argv = launch.argv
    assert argv[:7] == (
        sys.executable,
        "-m",
        "code_factory.runs.adapters.runner",
        str(plan.exit_file),
        "--timeout-seconds",
        str(plan.timeout_s),
        "--",
    )
    settings = json.loads(_after(argv, "--settings"))
    assert settings["sandbox"]["enabled"] is True
    assert settings["sandbox"]["allowUnsandboxedCommands"] is False
    hooks = settings["hooks"]

    def commands(event: str) -> set[str]:
        return {h["command"] for entry in hooks[event] for h in entry["hooks"]}

    assert "ask-hook" in commands("PermissionRequest")
    assert "guard-hook" in commands("PreToolUse")
    assert "recall-hook" in commands("SessionStart")
    server = json.loads(_after(argv, "--mcp-config"))["mcpServers"]["code-factory"]
    assert server == {
        "type": "http", "url": f"{BOARD}/mcp/",
        "headers": {"Authorization": "Bearer ${CODE_FACTORY_MCP_TOKEN}"},
    }  # fmt: skip
    assert "run-token" not in " ".join(argv)
    assert any(plan.ticket.id in word and "ticket/cf-1" in word for word in argv)


async def test_the_run_gets_its_token_and_never_the_boards_settings(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODE_FACTORY_DATABASE_URL", "postgresql://u:secret@h/x_test")
    monkeypatch.setenv("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", "1")
    monkeypatch.setenv("SOME_TOOL_SETTING", "kept")

    env = (await _launcher(app).launch(await _plan(app, tmp_path))).env

    assert (env["CODE_FACTORY_MCP_TOKEN"], env["CODE_FACTORY_URL"]) == ("run-token", BOARD)
    assert env["CODE_FACTORY_RUNS_DIR"] == str(tmp_path)  # the folder of the exit file
    assert "CODE_FACTORY_DATABASE_URL" not in env
    assert "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB" not in env
    assert env["SOME_TOOL_SETTING"] == "kept"


async def test_a_run_of_another_runtime_is_refused_with_what_to_do(
    app: FastAPI, tmp_path: Path
) -> None:
    launcher = _launcher(app)
    plan = await _plan(app, tmp_path, runtime="codex")
    with pytest.raises(UnavailableError, match="choose a connection in Agents"):
        await launcher.launch(plan)
    launcher = _launcher(app)
    plan = await _plan(app, tmp_path, runtime="unknown")
    with pytest.raises(UnavailableError, match="unsupported agent runtime"):
        await launcher.launch(plan)


async def test_a_board_that_is_not_served_starts_no_run(app: FastAPI, tmp_path: Path) -> None:
    launcher = _launcher(app, base_url="")
    plan = await _plan(app, tmp_path)
    with pytest.raises(UnavailableError) as refused:
        await launcher.launch(plan)
    assert str(refused.value) == NOT_SERVED


async def test_codex_uses_a_private_home_and_the_board_mcp_inside_the_sandbox(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def program(name: str, _places: tuple[Path, ...]) -> Path:
        return Path("/usr/local/bin") / name

    async def protected(_repository: str, _name: str) -> list[Path]:
        return [tmp_path / ".git/config"]

    monkeypatch.setattr(codex, "find_program", program)
    monkeypatch.setattr(app.state.services.get(GitService), "protected_paths", protected)
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-secret")
    await app.state.services.get(AgentService).add_connection(
        ConnectionChange(name="local", kind="ollama")
    )
    initial = await _plan(app, tmp_path, runtime="codex")
    plan = replace(
        initial, given=initial.given.model_copy(update={"connection": "local", "model": "example"})
    )
    launch = await _launcher(app).launch(plan)
    home = Path(launch.env["CODEX_HOME"])
    settings = tomllib.loads((home / "config.toml").read_text())
    sandbox = json.loads((home / "sandbox.json").read_text())

    assert launch.argv[7:10] == ("/usr/local/bin/srt", "--settings", str(home / "sandbox.json"))
    assert "codex exec --json --ephemeral" in launch.argv[-1]
    assert "run-token" not in " ".join(launch.argv)
    assert "OPENAI_API_KEY" not in launch.env
    assert launch.env["CODE_FACTORY_RUNS_DIR"] == str(tmp_path)
    assert settings["mcp_servers"]["code-factory"] == {
        "url": f"{BOARD}/mcp/",
        "bearer_token_env_var": "CODE_FACTORY_MCP_TOKEN",
        "required": True,
    }
    tree = str(await AsyncPath(tmp_path).resolve())
    assert settings["projects"][tree]["trust_level"] == "untrusted"
    assert sandbox["network"]["allowedDomains"] == ["127.0.0.1:4000", "localhost:11434"]
    assert str(tmp_path / ".git/config") in sandbox["filesystem"]["denyWrite"]
    assert "CODE_FACTORY_MCP_TOKEN" not in [v["name"] for v in sandbox["credentials"]["envVars"]]
    assert "CODE_FACTORY_MCP_TOKEN" in settings["shell_environment_policy"]["exclude"]


async def test_the_launch_refusal_is_known_before_anything_is_made(
    app: FastAPI, tmp_path: Path
) -> None:
    plan = await _plan(app, tmp_path)
    other = await _plan(app, tmp_path, runtime="codex")

    assert _launcher(app, base_url="").launch_refusal(plan.given) == NOT_SERVED
    assert _launcher(app).launch_refusal(other.given) is not None
    connected = other.given.model_copy(update={"connection": "chatgpt"})
    assert _launcher(app).launch_refusal(connected) is None
    assert _launcher(app).launch_refusal(plan.given) is None


STAND_IN = """#!/bin/sh
printf '%s\\n' "$@" > "$RECORD/args"
printf '%s' "$CODE_FACTORY_MCP_TOKEN" > "$RECORD/token"
echo started
exit 3
"""


async def test_the_launch_runs_in_the_real_wrapper_which_starts_the_agent_and_records_its_exit(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "bin"
    folder.mkdir()
    (folder / "claude").write_text(STAND_IN)
    (folder / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}:{os.environ['PATH']}")
    monkeypatch.setenv("RECORD", str(tmp_path))
    plan = await _plan(app, tmp_path)
    launch = await _launcher(app).launch(plan)

    done = await asyncio.create_subprocess_exec(
        *launch.argv, env=launch.env, cwd=tmp_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )  # fmt: skip
    output, _ = await done.communicate()

    args = (tmp_path / "args").read_text().splitlines()
    assert (done.returncode, output.decode().strip()) == (3, "started")
    assert plan.exit_file.read_text().strip() == "3"
    assert (tmp_path / "token").read_text() == "run-token"
    assert args[args.index("--permission-mode") + 1] == "acceptEdits"
    assert "--strict-mcp-config" in args
