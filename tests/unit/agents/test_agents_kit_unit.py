"""The kit passes through every public rule of its rule files, and the service redacts every
context it keeps."""

import inspect

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
from code_factory.agents.service import StartKit

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
