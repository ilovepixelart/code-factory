"""Launch Codex with per-run configuration and the board's connection."""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from anyio import Path as AsyncPath
from anyio.to_thread import run_sync

from code_factory.agents.models import ConnectionDefinition
from code_factory.agents.service import AgentService
from code_factory.broker.service import BrokerService
from code_factory.git.service import GitService
from code_factory.platform.contained import SANDBOX_PROGRAM
from code_factory.platform.errors import UnavailableError
from code_factory.platform.programs import find_program
from code_factory.platform.served import Served
from code_factory.platform.services import Services
from code_factory.runs.adapters import files
from code_factory.runs.adapters.runner.wrapper import RUNS_VARIABLE
from code_factory.runs.ports import Launch, LaunchPlan

MCP_TOKEN = "CODE_FACTORY_MCP_TOKEN"  # noqa: S105  # variable name
BROKER_TOKEN = "CODE_FACTORY_CODEX_TOKEN"  # noqa: S105  # variable name
CODEX_CONNECTION = "choose a connection in Agents before starting a codex run"
RUNNER = ("-m", "code_factory.runs.adapters.runner")


def run_folder(state: Path, run_id: str) -> Path:
    """The isolated configuration and scratch directory of a run."""
    return state / "runs" / f"{run_id}.codex"


class CodexLauncher:
    """An isolated Codex CLI with the normal run wrapper, MCP and provider broker."""

    def __init__(self, services: Services, state: Path) -> None:
        self._services = services
        self._state = state
        self._resolved = state.resolve()

    async def launch(self, plan: LaunchPlan, prompt: str) -> Launch:
        """Build the supervised command inside an outer sandbox."""
        agents = self._services.get(AgentService)
        connection = await agents.connection_definition(plan.given.connection)
        paths = (self._state, plan.tree.path)
        codex = await find_program("codex", paths)
        if codex is None:
            raise UnavailableError("codex is not on a trusted PATH; install the Codex CLI")
        srt = await find_program(SANDBOX_PROGRAM, paths)
        if srt is None:
            raise UnavailableError(
                "srt is not on a trusted PATH; install @anthropic-ai/sandbox-runtime"
            )

        protected = await self._services.get(GitService).protected_paths(
            plan.ticket.repository, plan.tree.name
        )
        model_config, model_host, token = await self._provider(plan, connection)
        board = self._services.get(Served)
        home = run_folder(self._state, plan.run_id)
        config = home / "config.toml"
        sandbox = home / "sandbox.json"
        program = await run_sync(
            agents.kit.codex_program_folder,
            str(Path.home()),
            str(self._state),
            str(codex),
            os.path.realpath,
        )
        tree = str(await AsyncPath(plan.tree.path).resolve())
        await files.write_atomic(config, self._config(tree, board, model_config))
        await files.write_atomic(
            sandbox,
            agents.kit.process_settings(
                state=agents.kit.state_forms(str(self._state), str(self._resolved)),
                hosts=[f"127.0.0.1:{board.port}", model_host],
                writes=[tree, str(home)],
                denied=[str(config), str(sandbox), *(str(path) for path in protected)],
                reads=[str(home), tree, *([program] if program is not None else [])],
                keys=[],
                keep_mcp=True,
            ),
        )
        env = self._environment(plan, home, token)
        # srt already applies the filesystem and network policy to the whole process.
        # Nesting Codex's sandbox inside it blocks commands on macOS.
        _, entry = agents.kit.shell_words(agents.kit.runtime_template("codex"))
        command = [
            str(codex), entry, "--json", "--ephemeral", "--ignore-rules",
            "--sandbox", "danger-full-access",
            "-c", "features.default_mode_request_user_input=false",
            "-m", plan.given.model, "--", prompt,
        ]  # fmt: skip
        argv = (
            sys.executable, *RUNNER, str(plan.exit_file),
            "--timeout-seconds", str(plan.timeout_s), "--",
            *agents.kit.contained(str(srt), str(sandbox), command),
        )  # fmt: skip
        return Launch(argv=argv, env=env, digest=agents.kit.digest(prompt))

    async def _provider(
        self, plan: LaunchPlan, connection: ConnectionDefinition
    ) -> tuple[str, str, str]:
        agents = self._services.get(AgentService)
        if connection.kind != "codex-login" and not connection.key_env:
            model = await agents.run_connection(connection.name, plan.given.model, "codex")
            return model.config_env, agents.model_host(connection), ""
        broker = self._services.get(BrokerService)
        endpoint = broker.endpoints(connection.name)
        port = urlsplit(endpoint.proxy_url).port
        assert port is not None  # noqa: S101  # broker endpoints always include the bound port
        model = await agents.run_connection(connection.name, plan.given.model, "codex", broker=port)
        cap = (
            Decimal(str(plan.remaining))
            if plan.remaining is not None and connection.kind != "codex-login"
            else None
        )
        issued = await broker.issue_run_token(
            plan.run_id, connection.name, cap,
            datetime.now(UTC) + timedelta(seconds=plan.lifetime_s),
        )  # fmt: skip
        return model.config_env, f"127.0.0.1:{port}", issued.token.get_secret_value()

    def _config(self, tree: str, board: Served, model: str) -> str:
        agents = self._services.get(AgentService)
        url = json.dumps(f"{board.base_url.rstrip('/')}/mcp/")
        return (
            'approval_policy = "never"\n'
            + model
            + "\n[shell_environment_policy]\n"
            + 'inherit = "all"\n'
            + f'exclude = ["{MCP_TOKEN}", "{BROKER_TOKEN}", "CODEX_HOME"]\n'
            + "\n[mcp_servers.code-factory]\n"
            + f'url = {url}\nbearer_token_env_var = "{MCP_TOKEN}"\nrequired = true\n\n'
            + agents.kit.codex_untrusted(tree)
        )

    def _environment(self, plan: LaunchPlan, home: Path, token: str) -> dict[str, str]:
        kit = self._services.get(AgentService).kit
        excluded = set(kit.left_out("codex", os.environ))
        return {
            **{name: value for name, value in os.environ.items() if name not in excluded},
            **kit.agent_identity(None),
            "CODEX_HOME": str(home),
            MCP_TOKEN: plan.token,
            RUNS_VARIABLE: str(plan.exit_file.parent),
            **({BROKER_TOKEN: token} if token else {}),
        }
