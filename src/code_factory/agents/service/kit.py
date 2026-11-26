"""The pure parts of starting an agent, for the modules that start one.

Other modules may import only `service` and `models`, so each public rule they need is passed
through here. A test asserts every public rule of the kit's rule files has a pass-through.
"""

from pathlib import Path

from code_factory.agents.models.agents import AgentDefinition
from code_factory.agents.models.progress import ChangedFiles, RunProgress
from code_factory.agents.models.usage import LogUsage
from code_factory.agents.repository import AgentRepository
from code_factory.agents.rules import (
    codemap,
    command,
    fence,
    hooks,
    inherited,
    limits,
    logs,
    mounts,
    permissions,
    places,
    progress,
    prompt,
    settings,
    spending,
    srt,
    tasks,
    telemetry,
)
from code_factory.agents.rules import harness as harness_rules
from code_factory.agents.rules.command import CommandParts
from code_factory.agents.rules.commands import runtime_template
from code_factory.agents.rules.environment import codex_untrusted
from code_factory.agents.rules.fence import RedactedStream, Redaction
from code_factory.agents.rules.telemetry import Receiver
from code_factory.agents.service.base import Shared

__all__ = ["CommandParts", "KitService", "Receiver", "RedactedStream", "Redaction", "StartKit"]


class StartKit:
    """One synchronous pass-through per public rule of the starting kit."""

    runtime_template = staticmethod(runtime_template)
    codex_untrusted = staticmethod(codex_untrusted)
    shell_words = staticmethod(command.shell_words)
    command_for = staticmethod(command.command_for)
    digest = staticmethod(fence.digest)
    context_block = staticmethod(fence.context_block)
    unmarked = staticmethod(fence.unmarked)
    prompt_refusal = staticmethod(fence.prompt_refusal)
    placeholder = staticmethod(fence.placeholder)
    checked_nonce = staticmethod(fence.checked_nonce)
    plain = staticmethod(fence.plain)
    neutralised = staticmethod(fence.neutralised)
    one_line = staticmethod(fence.one_line)
    with_permission_hook = staticmethod(hooks.with_permission_hook)
    with_tell_hook = staticmethod(hooks.with_tell_hook)
    with_capture_hooks = staticmethod(hooks.with_capture_hooks)
    with_rewrite_guard = staticmethod(hooks.with_rewrite_guard)
    mcp_config = staticmethod(hooks.mcp_config)
    mcp_http_config = staticmethod(hooks.mcp_http_config)
    run_settings = staticmethod(settings.run_settings)
    denied_files = staticmethod(settings.denied_files)
    denied_variables = staticmethod(settings.denied_variables)
    sandbox_settings = staticmethod(settings.sandbox_settings)
    telemetry_env = staticmethod(telemetry.telemetry_env)
    max_iterations = staticmethod(telemetry.max_iterations)
    left_out = staticmethod(inherited.left_out)
    uncontained_left_out_of = staticmethod(inherited.uncontained_left_out_of)
    unreadable_names = staticmethod(inherited.unreadable_names)
    log_usage = staticmethod(logs.log_usage)
    spent_note = staticmethod(logs.spent_note)
    month_spent_note = staticmethod(logs.month_spent_note)
    log_cost = staticmethod(logs.log_cost)
    log_model = staticmethod(logs.log_model)
    log_tokens = staticmethod(logs.log_tokens)
    log_cache_reads = staticmethod(logs.log_cache_reads)
    log_turns = staticmethod(logs.log_turns)
    usage_limit = staticmethod(limits.usage_limit)
    codex_reset = staticmethod(limits.codex_reset)
    agent_price = staticmethod(spending.agent_price)
    estimate = staticmethod(spending.estimate)
    spent_parts = staticmethod(spending.spent_parts)
    costs_so_far = staticmethod(spending.costs_so_far)
    ticket_budget = staticmethod(spending.ticket_budget)
    monthly_budget = staticmethod(spending.monthly_budget)
    tool_counts = staticmethod(progress.tool_counts)
    run_progress = staticmethod(progress.run_progress)
    changed_files = staticmethod(progress.changed_files)
    board_ships = tasks.BOARD_SHIPS
    built_in_task = staticmethod(tasks.built_in_task)
    stage_instructions = staticmethod(tasks.stage_instructions)
    fill_task = staticmethod(tasks.fill_task)
    plan_first = staticmethod(tasks.plan_first)
    rules_in_use_note = staticmethod(tasks.rules_in_use_note)
    review_guide_note = staticmethod(tasks.review_guide_note)
    role_notes = staticmethod(tasks.role_notes)
    guardrail_note = staticmethod(tasks.guardrail_note)
    code_map = staticmethod(codemap.code_map)
    stage_task = staticmethod(tasks.stage_task)
    build_prompt = staticmethod(prompt.build_prompt)
    is_outside = staticmethod(prompt.is_outside)
    unfenced = staticmethod(prompt.unfenced)
    harness = staticmethod(harness_rules.harness)
    named_files = staticmethod(harness_rules.named_files)
    place_note = staticmethod(harness_rules.place_note)
    in_container = staticmethod(mounts.in_container)
    container_mount = staticmethod(mounts.container_mount)
    secret_paths = staticmethod(mounts.secret_paths)
    mount_reaches_secrets = staticmethod(mounts.mount_reaches_secrets)
    checks_image_tag = staticmethod(mounts.checks_image_tag)
    summary = staticmethod(permissions.summary)
    shown_whole = staticmethod(permissions.shown_whole)
    request_kind = staticmethod(permissions.request_kind)
    standing_rules = staticmethod(permissions.standing_rules)
    answer_history = staticmethod(permissions.answer_history)
    suggestions = staticmethod(permissions.suggestions)
    outside_tree = staticmethod(permissions.outside_tree)
    routine = staticmethod(permissions.routine)
    refused_in_a_row = staticmethod(permissions.refused_in_a_row)
    escalation = staticmethod(permissions.escalation)
    state_forms = staticmethod(places.state_forms)
    lock_folder = staticmethod(places.lock_folder)
    lock_folders = staticmethod(places.lock_folders)
    run_writes = staticmethod(places.run_writes)
    kept_writes = staticmethod(places.kept_writes)
    checkout_denials = staticmethod(places.checkout_denials)
    allowed_domains = staticmethod(places.allowed_domains)
    host_port = staticmethod(places.host_port)
    model_host = staticmethod(places.model_host)
    contained_line = staticmethod(places.contained_line)
    contained = staticmethod(places.contained)
    agent_identity = staticmethod(places.agent_identity)
    codex_program_folder = staticmethod(places.codex_program_folder)
    process_settings = staticmethod(srt.process_settings)
    tree_settings = staticmethod(srt.tree_settings)
    preview_settings = staticmethod(srt.preview_settings)
    git_settings = staticmethod(srt.git_settings)


class KitService(Shared):
    """The kit and the readers of a run's log."""

    kit = StartKit()

    async def redaction(self, keys: list[str] | None = None) -> Redaction | None:
        """What keeps every agent's context, current and kept, and `keys` out of a log."""
        async with self._uow() as session:
            agents = await AgentRepository(session).all()
        return Redaction.of_contexts(_contexts(agents), keys)

    async def usage_of_log(self, path: Path) -> LogUsage:
        """What the run log at `path` reports; nothing for a link, a missing or an oversize log."""
        lines = await self._logs.lines(path)
        return LogUsage() if lines is None else logs.log_usage(lines)

    async def progress_of(
        self, path: Path, reported_tokens: int | None, changed: ChangedFiles | None
    ) -> RunProgress:
        """What the run logging to `path` has done so far.

        Nothing is known of a link, a missing log or one past 64 MiB. `reported_tokens` is what
        the run reported to the board; `changed` the files its worktree changed.
        """
        stamped = await self._logs.stamped(path)
        if stamped is None:
            return progress.run_progress(None, reported_tokens, changed, None)
        lines, grew = stamped
        return progress.run_progress(lines, reported_tokens, changed, grew)


def _contexts(agents: list[AgentDefinition]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for agent in agents:
        if agent.context is not None:
            found.append((agent.name, agent.context))
        found += [(agent.name, version.context) for version in agent.context_history]
    return found
