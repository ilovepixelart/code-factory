"""The kit passes through every public rule of its rule files, and the service redacts every
context it keeps."""

import inspect
import os
from pathlib import Path

import pytest

from agents_support import agents_fixture, clock_fixture, store_fixture  # noqa: F401
from code_factory.agents.adapters import files as files_module
from code_factory.agents.models.agents import AgentChange
from code_factory.agents.models.progress import ChangedFiles, RunProgress
from code_factory.agents.rules import (
    command,
    fence,
    harness,
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
from code_factory.agents.service import AgentService, StartKit

# Public functions the kit does not pass through: helpers the service itself uses or data.
INTERNAL = {"records", "amount"}
CONTRACT = {
    command: {"shell_words", "command_for"},
    fence: {
        "digest",
        "context_block",
        "unmarked",
        "prompt_refusal",
        "placeholder",
        "checked_nonce",
        "plain",
        "neutralised",
        "one_line",
    },
    hooks: {
        "with_permission_hook",
        "with_tell_hook",
        "with_capture_hooks",
        "with_rewrite_guard",
        "mcp_config",
    },
    settings: {"run_settings", "denied_files", "denied_variables", "sandbox_settings"},
    telemetry: {"telemetry_env", "max_iterations"},
    inherited: {
        "left_out",
        "uncontained_left_out_of",
        "unreadable_names",
    },
    logs: {
        "log_usage",
        "spent_note",
        "month_spent_note",
        "log_cost",
        "log_model",
        "log_tokens",
        "log_cache_reads",
        "log_turns",
    },
    limits: {"usage_limit", "codex_reset"},
    spending: {
        "agent_price",
        "estimate",
        "spent_parts",
        "costs_so_far",
        "ticket_budget",
        "monthly_budget",
    },
    progress: {"tool_counts", "run_progress", "changed_files"},
    tasks: {
        "built_in_task",
        "stage_instructions",
        "fill_task",
        "plan_first",
        "rules_in_use_note",
        "review_guide_note",
        "stage_task",
    },
    prompt: {"build_prompt", "is_outside", "unfenced"},
    harness: {"harness", "named_files", "place_note"},
    mounts: {
        "in_container",
        "container_mount",
        "secret_paths",
        "mount_reaches_secrets",
        "checks_image_tag",
    },
    permissions: {
        "summary",
        "shown_whole",
        "request_kind",
        "standing_rules",
        "answer_history",
        "suggestions",
        "outside_tree",
        "routine",
        "refused_in_a_row",
        "escalation",
    },
    places: {
        "state_forms",
        "lock_folder",
        "lock_folders",
        "run_writes",
        "kept_writes",
        "checkout_denials",
        "allowed_domains",
        "host_port",
        "model_host",
        "contained_line",
        "contained",
        "agent_identity",
        "codex_program_folder",
    },
    srt: {"process_settings", "tree_settings", "preview_settings", "git_settings"},
}


def test_every_public_rule_of_the_kit_files_has_a_pass_through() -> None:
    for module, names in CONTRACT.items():
        public = {
            name
            for name, item in inspect.getmembers(module, inspect.isfunction)
            if not name.startswith("_") and item.__module__ == module.__name__
        }
        missing = {name for name in public - INTERNAL if not hasattr(StartKit, name)}
        assert missing == set(), f"{module.__name__}: {sorted(missing)}"
        assert names <= public


def test_no_credential_name_filter_is_offered_since_inheritance_is_an_allowlist() -> None:
    assert not hasattr(StartKit, "credential_named")
    assert not hasattr(inherited, "credential_named")
    assert not hasattr(inherited, "CREDENTIAL_ENDINGS")


def test_a_pass_through_is_the_rule_itself() -> None:
    assert StartKit.shell_words("a 'b c'") == ["a", "b c"]
    assert StartKit.digest("abc") == "ba7816bf8f01"
    assert StartKit.runtime_template("codex") == "codex exec"


async def test_the_redaction_covers_every_current_and_kept_context_and_the_keys(
    agents: AgentService,
) -> None:
    await agents.add_agent(AgentChange(name="w"))
    await agents.edit_agent("w", AgentChange(context="first context"))
    await agents.edit_agent("w", AgentChange(context="second context"))
    redaction = await agents.redaction(["sk-key"])
    assert redaction is not None
    assert redaction.apply("a first context b second context c sk-key") == (
        "a [owner context for w, 13 characters] b [owner context for w, 14 characters] "
        "c [redacted key]"
    )


async def test_without_a_context_or_a_key_there_is_no_redaction(agents: AgentService) -> None:
    await agents.add_agent(AgentChange(name="w"))
    assert await agents.redaction() is None


async def test_a_log_is_read_for_its_usage_and_a_link_or_missing_log_reports_nothing(
    agents: AgentService, tmp_path: Path
) -> None:
    log = tmp_path / "run.log"
    log.write_text('{"type":"result","total_cost_usd":0.12}\n', encoding="utf-8")
    link = tmp_path / "link.log"
    link.symlink_to(log)
    assert (await agents.usage_of_log(log)).cost == 0.12
    assert (await agents.usage_of_log(link)).cost is None
    assert (await agents.usage_of_log(tmp_path / "absent.log")).cost is None


TOOL = (
    '{"type":"assistant","message":{"id":"m1","content":[{"type":"tool_use","id":"t1",'
    '"name":"Edit","input":{}}],"usage":{"input_tokens":10,"output_tokens":2}}}\n'
)


async def test_a_logs_progress_has_its_counts_tokens_files_and_the_time_it_last_grew(
    agents: AgentService, tmp_path: Path
) -> None:
    log = tmp_path / "run.log"
    log.write_text(TOOL, encoding="utf-8")
    os.utime(log, (1_790_000_123, 1_790_000_123))
    files = ChangedFiles(count=1, names=("a.py",))
    got = await agents.progress_of(log, 5, files)
    assert got == RunProgress(
        tool_calls=1, reads=0, changes=1, files=files, tokens=12, last_activity=1_790_000_123.0
    )
    assert (await agents.progress_of(log, 900, None)).tokens == 900


async def test_a_link_a_missing_log_and_a_log_past_the_bound_say_nothing_of_its_run(
    agents: AgentService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "run.log"
    log.write_text(TOOL, encoding="utf-8")
    link = tmp_path / "link.log"
    link.symlink_to(log)
    nothing = RunProgress()
    assert await agents.progress_of(link, None, None) == nothing
    assert await agents.progress_of(tmp_path / "absent.log", None, None) == nothing
    assert (await agents.progress_of(log, None, None)).tool_calls == 1
    monkeypatch.setattr(files_module, "MAX_LOG", len(TOOL) - 1)
    assert await agents.progress_of(log, None, None) == nothing
    monkeypatch.setattr(files_module, "MAX_LOG", len(TOOL))
    assert (await agents.progress_of(log, None, None)).tool_calls == 1
