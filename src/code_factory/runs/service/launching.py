"""The command and environment one run starts with: its prompt, settings, MCP server and sandbox.

A claude run carries its sandbox in `--settings`: commands reach no host and no secret and write
only the worktree and the gate's lock folder; its hooks ask the board before a tool runs, tell it
what was said and record the session. The run's environment is this process's without the
variables a run may not read and the board's own settings, plus its connection's, its MCP token
and the board's address.
"""

import logging
import os
import secrets
import sys

from code_factory.agents.models import PromptParts
from code_factory.agents.service import AgentService, CommandParts
from code_factory.git.service import GitService
from code_factory.platform.config import Settings
from code_factory.platform.errors import CodeFactoryError, UnavailableError
from code_factory.platform.served import Served
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.runs.adapters.runner.wrapper import RUNS_VARIABLE
from code_factory.runs.ports import Given, HookCommandSource, Launch, LaunchPlan
from code_factory.runs.service.codex import CODEX_CONNECTION, CodexLauncher
from code_factory.runs.service.permissions import PermissionService
from code_factory.sessions.service import SessionService
from code_factory.settings.service import SettingsService
from code_factory.talk.service import TalkService
from code_factory.tickets.service import TicketService

RUNNER = ("-m", "code_factory.runs.adapters.runner")
MCP_TOKEN_VARIABLE = "CODE_FACTORY_MCP_TOKEN"  # noqa: S105  # a name, not a secret
URL_VARIABLE = "CODE_FACTORY_URL"
# Set, it forces the runtime into the default permission mode whatever the agent names; the
# sandbox's credential rules keep the keys from the agent's commands instead.
SCRUB_VARIABLE = "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"
NONCE_BYTES = 12
# The board's own settings, its database address and password among them, never reach a run.
BOARD_PREFIX = "CODE_FACTORY_"


NOT_SERVED = (
    "a run reaches the board's MCP server and hooks over HTTP, so runs start only on a served "
    "board: run code-factory serve"
)


logger = logging.getLogger(__name__)

# The stages that work out where a change goes, so they are given the code map.
MAPPED_STAGES = ("spec", "build")


class RunLauncher:
    """Builds the `Launch` of a run from the neighbours that own each part."""

    def __init__(self, services: Services, settings: Settings, hooks: HookCommandSource) -> None:
        self._services = services
        self._hooks = hooks
        self._codex = CodexLauncher(services, settings.state_dir)
        home = settings.state_dir
        self._home = str(home)
        self._resolved = str(home.resolve())
        self._resolved_parent = str(home.resolve().parent)

    def launch_refusal(self, given: Given) -> str | None:
        """Why no run of `given` can launch now, `None` when one can; nothing is made to ask."""
        if given.runtime not in {"claude", "codex"}:
            return f"unsupported agent runtime {given.runtime}; choose Claude or Codex in Agents"
        if given.runtime == "codex" and not given.connection:
            return CODEX_CONNECTION
        if not self._services.get(Served).serving:
            return NOT_SERVED
        return None

    async def launch(self, plan: LaunchPlan) -> Launch:
        """The wrapper's command line and the run's environment."""
        given = plan.given
        if (refusal := self.launch_refusal(given)) is not None:
            raise UnavailableError(refusal)
        prompt = await self._prompt(plan)
        if given.runtime == "codex":
            return await self._codex.launch(plan, prompt)
        kit = self._services.get(AgentService).kit
        resolved = await self._services.get(AgentService).resolve_agent(given.agent or None)
        command = kit.command_for(
            resolved.setup.template or kit.runtime_template(given.runtime),
            CommandParts(
                prompt=prompt,
                permissions=plan.permissions,
                remaining=plan.remaining,
                settings=await self._run_settings(),
                model=given.model,
                mcp=kit.mcp_http_config(self._mcp_url()),
                local=given.local,
            ),
        )
        argv = (
            sys.executable, *RUNNER, str(plan.exit_file),
            "--timeout-seconds", str(plan.timeout_s), "--", *command,
        )  # fmt: skip
        return Launch(argv=argv, env=await self._env(plan), digest=kit.digest(prompt))

    async def _prompt(self, plan: LaunchPlan) -> str:
        kit = self._services.get(AgentService).kit
        if plan.prompt is not None:
            prompt = plan.prompt
        else:
            ticket = await self._services.get(TicketService).get(plan.ticket.id)
            task = kit.stage_task(
                kit.fill_task(
                    kit.built_in_task(plan.stage), ticket.id, ticket.tests or "", ticket.e2e or ""
                ),
                plan.stage,
                roles=await self._review_notes(ticket.repository) if plan.stage == "review" else "",
            )
            if plan.stage in MAPPED_STAGES:
                task = "\n\n".join(p for p in (task, await self._map(ticket.repository)) if p)
            waiting = await self._services.get(TalkService).pending_messages(ticket.id)
            prompt = kit.build_prompt(
                PromptParts(
                    ticket_id=ticket.id,
                    title=ticket.title,
                    kind=plan.ticket.kind,
                    branch=plan.tree.branch,
                    stage=plan.stage,
                    task=task,
                    nonce=secrets.token_hex(NONCE_BYTES),
                    source=plan.ticket.source,
                    messages=tuple(m.text for m in waiting),
                )
            )
        return prompt if plan.nudge is None else f"{prompt}\n\n{plan.nudge}"

    async def _map(self, repository: str) -> str:
        """The repository's code map; empty when its files cannot be listed, which no run needs."""
        try:
            files = await self._services.get(GitService).tracked_files(repository)
        except CodeFactoryError as error:
            logger.warning("runs: no code map of %s: %s", repository, error)
            return ""
        return self._services.get(AgentService).kit.code_map(files)

    async def _review_notes(self, repository: str) -> str:
        """What the repository's config adds to a review: its roles, then its guardrails."""
        kit = self._services.get(AgentService).kit
        try:
            root = await self._services.get(RepositoryService).get(repository)
            agents = (await self._services.get(SettingsService).load(root)).agents
        except CodeFactoryError as error:
            logger.warning("runs: no review roles of %s: %s", repository, error)
            return ""
        if agents is None:
            return ""
        notes = [
            kit.role_notes(list(agents.review_roles or [])),
            kit.guardrail_note(list(agents.sensitive_paths or []), agents.large_change),
        ]
        return "\n\n".join(note for note in notes if note)

    async def _run_settings(self) -> str:
        kit = self._services.get(AgentService).kit
        hooks = self._hooks.run_hooks()
        capture = self._services.get(SessionService).capture_hook()
        rules = await self._services.get(PermissionService).rules()
        settings = kit.with_permission_hook(rules, approval=True, command=hooks.permission)
        settings = kit.with_capture_hooks(settings, capture.command, hooks.recall)
        settings = kit.with_rewrite_guard(kit.with_tell_hook(settings, hooks.tell), hooks.rewrite)
        return kit.run_settings(
            state=kit.state_forms(self._home, self._resolved),
            hooks=settings,
            sandbox=True,
            kept=[],
            locks=kit.lock_folders(self._home, self._resolved_parent),
            keys=[],
        )

    def _mcp_url(self) -> str:
        served = self._services.get(Served)
        return f"{served.base_url.rstrip('/')}/mcp/"

    async def _env(self, plan: LaunchPlan) -> dict[str, str]:
        kit = self._services.get(AgentService).kit
        unreadable = set(kit.unreadable_names(os.environb.keys()))
        env = {
            name: value
            for name, value in os.environ.items()
            if os.fsencode(name) not in unreadable and not name.startswith(BOARD_PREFIX)
        }
        env.pop(SCRUB_VARIABLE, None)
        if plan.given.connection:
            connection = await self._services.get(AgentService).run_connection(
                plan.given.connection, plan.given.model, plan.given.runtime
            )
            for name, value in connection.env.items():
                if value is None:
                    env.pop(name, None)
                else:
                    env[name] = value.get_secret_value()
        env[MCP_TOKEN_VARIABLE] = plan.token
        env[URL_VARIABLE] = self._services.get(Served).base_url
        env[RUNS_VARIABLE] = str(plan.exit_file.parent)
        return env
