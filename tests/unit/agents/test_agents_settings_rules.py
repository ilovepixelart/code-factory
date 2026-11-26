"""A run's settings, hooks, MCP configuration and telemetry against the previous
implementation's `runs.golden.json` (settings and telemetry cases, with `{exe}` and `{home}` kept as
placeholders and the old name never present)."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretBytes

from code_factory.agents.models.constants import SECRET_FILES, SECRET_VARIABLES
from code_factory.agents.rules.hooks import (
    MCP_TOKEN_VARIABLE,
    mcp_config,
    with_capture_hooks,
    with_permission_hook,
    with_rewrite_guard,
    with_tell_hook,
)
from code_factory.agents.rules.settings import denied_files, denied_variables, run_settings
from code_factory.agents.rules.telemetry import Receiver, max_iterations, telemetry_env

GOLDEN = Path(__file__).parents[2] / "support/golden" / "agents"
EXE = '"{exe}"'


def golden(name: str) -> str:
    return json.dumps(json.loads((GOLDEN / name).read_text(encoding="utf-8")))


def hooks(rules: list[str], *, approval: bool) -> dict[str, Any]:
    given = with_permission_hook(rules, approval=approval, command=f"{EXE} gate permission")
    return with_capture_hooks(given, f"{EXE} capture", f"{EXE} recall")


def test_the_gated_run_settings_are_the_golden_json_byte_for_byte() -> None:
    text = run_settings(
        state=["{home}"],
        hooks=hooks(["Read"], approval=True),
        sandbox=True,
        kept=[],
        locks=[],
        keys=[],
    )
    assert text == golden("run_settings.json")


def test_without_approval_and_sandbox_only_the_denies_and_capture_hooks_remain() -> None:
    text = run_settings(
        state=["{home}"],
        hooks=hooks(["Bash(npm test *)", "Edit"], approval=False),
        sandbox=False,
        kept=[],
        locks=[],
        keys=[],
    )
    assert text == golden("run_settings_no_sandbox.json")
    parsed = json.loads(text)
    assert "sandbox" not in parsed
    assert "Read(~/.ssh)" in parsed["permissions"]["deny"]


@pytest.mark.parametrize("sandbox", [True, False])
def test_every_secret_file_and_the_state_folder_are_denied_either_way(sandbox: bool) -> None:
    parsed = json.loads(
        run_settings(state=["/s"], hooks=None, sandbox=sandbox, kept=["/k"], locks=[], keys=[])
    )
    deny = parsed["permissions"]["deny"]
    for path in SECRET_FILES:
        assert f"Read({path})" in deny
        assert f"Read({path}/**)" in deny
    assert {"Read(//s)", "Edit(//s)", "Edit(//k)", "Edit(//k/**)"} <= set(deny)


def test_the_sandbox_denies_every_secret_variable_the_runtimes_keys_and_each_connection_key() -> (
    None
):
    sandbox = json.loads(
        run_settings(
            state=[],
            hooks=None,
            sandbox=True,
            kept=["/k"],
            locks=["/l"],
            keys=["OPENROUTER_API_KEY"],
        )
    )["sandbox"]
    names = [item["name"] for item in sandbox["credentials"]["envVars"]]
    assert names == [
        *SECRET_VARIABLES,
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CODE_FACTORY_MCP_TOKEN",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_LOGS_HEADERS",
        "OPENROUTER_API_KEY",
    ]
    assert sandbox["filesystem"]["allowWrite"] == ["/l"]
    assert sandbox["filesystem"]["denyWrite"] == ["/k"]
    assert sandbox["network"]["allowedDomains"] == []
    assert [f["path"] for f in sandbox["credentials"]["files"]] == list(SECRET_FILES)


def test_the_keychain_folders_are_not_in_the_secret_list_so_the_sandbox_denies_the_home() -> None:
    parsed = json.loads(
        run_settings(state=["/home/u"], hooks=None, sandbox=True, kept=[], locks=[], keys=[])
    )
    assert parsed["sandbox"]["filesystem"]["denyRead"] == ["/home/u"]
    assert denied_files(["/home/u"], [])[-4:] == [
        "Read(//home/u)",
        "Read(//home/u/**)",
        "Edit(//home/u)",
        "Edit(//home/u/**)",
    ]


def test_the_tell_and_guard_hooks_are_added_beside_the_groups_that_were_there() -> None:
    base = hooks([], approval=True)
    told = with_tell_hook(base, f"{EXE} gate tell")
    guarded = with_rewrite_guard(told, f"{EXE} gate rewrite")
    post = guarded["hooks"]["PostToolUse"]  # type: ignore[index]
    assert [g["hooks"][0]["command"] for g in post] == [f"{EXE} capture", f"{EXE} gate tell"]
    assert len(guarded["hooks"]["PostToolUseFailure"]) == 2  # type: ignore[index]
    pre = guarded["hooks"]["PreToolUse"]  # type: ignore[index]
    assert pre[-1] == {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": f"{EXE} gate rewrite", "timeout": 30}],
    }
    assert with_rewrite_guard(guarded, f"{EXE} gate rewrite") is guarded
    assert base["hooks"]["PostToolUse"] == [  # type: ignore[index]
        {"hooks": [{"type": "command", "command": f"{EXE} capture"}]}
    ]


def test_capture_hooks_are_added_once_and_a_narrow_recall_matcher_widens() -> None:
    twice = with_capture_hooks(hooks([], approval=False), f"{EXE} capture", f"{EXE} recall")
    assert len(twice["hooks"]["SessionStart"]) == 2
    old = {
        "hooks": {"SessionStart": [{"matcher": "startup", "hooks": [{"command": f"{EXE} recall"}]}]}
    }
    widened = with_capture_hooks(old, f"{EXE} capture", f"{EXE} recall")
    assert widened["hooks"]["SessionStart"][0]["matcher"] == "startup|resume|clear|compact"


def test_the_mcp_config_names_the_token_variable_and_never_a_token_value() -> None:
    config = json.loads(mcp_config("/bin/code-factory"))
    assert config == {
        "mcpServers": {
            "code-factory": {
                "command": "/bin/code-factory",
                "args": ["mcp"],
                "env": {"CODE_FACTORY_MCP_TOKEN": "${CODE_FACTORY_MCP_TOKEN}"},
            }
        }
    }
    everything = mcp_config("x") + run_settings(
        state=[], hooks=hooks([], approval=True), sandbox=True, kept=[], locks=[], keys=[]
    )
    assert "cfr_" not in everything


PREFIX = "code_factory."


def env(
    *,
    endpoint: str | None = "http://localhost:4317",
    protocol: str | None = None,
    stage: str = "review",
    receiver: Receiver | None = None,
) -> dict[str, str]:
    return telemetry_env(
        endpoint=endpoint,
        protocol=protocol,
        ticket_id="CF-1",
        run_id="abc123def456",
        stage=stage,
        repository="sample",
        receiver=receiver,
    )


def test_the_endpoint_gives_metrics_events_and_the_attributes_of_the_golden_case() -> None:
    assert env() == {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
        "OTEL_RESOURCE_ATTRIBUTES": (
            f"{PREFIX}ticket=CF-1,{PREFIX}run=abc123def456,{PREFIX}stage=review,"
            f"{PREFIX}repository=sample"
        ),
    }
    assert env(protocol="http/protobuf")["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/protobuf"


def test_a_stage_with_forbidden_bytes_keeps_only_the_printable_safe_ones() -> None:
    stage = 'custom stage;é,"x"'
    assert f"{PREFIX}stage=custom_stage____x_," in env(stage=stage)["OTEL_RESOURCE_ATTRIBUTES"]


def test_no_destination_means_no_telemetry_and_a_blank_endpoint_is_none() -> None:
    assert env(endpoint=None) == {}
    assert env(endpoint="") == {}


def test_the_board_receiver_gets_the_events_with_a_token_of_that_run_only() -> None:
    receiver = Receiver("http://127.0.0.1:9", SecretBytes(b"\x01" * 32))
    only = env(endpoint=None, receiver=receiver)
    assert list(only) == [
        "CLAUDE_CODE_ENABLE_TELEMETRY",
        "OTEL_LOGS_EXPORTER",
        "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_HEADERS",
        "OTEL_RESOURCE_ATTRIBUTES",
    ]
    assert only["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] == "http://127.0.0.1:9/v1/logs"
    expected = hashlib.sha256(b"\x01" * 32 + b"abc123def456").hexdigest()
    assert only["OTEL_EXPORTER_OTLP_LOGS_HEADERS"] == f"x-code-factory-token={expected}"
    assert receiver.token("other") != receiver.token("abc123def456")
    assert "01" * 8 not in repr(receiver)


@pytest.mark.parametrize(
    ("given", "cap"),
    [(12, 12), (3, 3), (1, 1), (0, 12), (-1, 12), (True, 12), ("3", 12), (None, 12)],
)
def test_the_iteration_cap_is_a_positive_whole_number_else_12(given: object, cap: int) -> None:
    assert max_iterations(given) == cap


@pytest.mark.parametrize("sandbox", [True, False])
def test_the_file_tools_cannot_write_the_claude_folder_of_the_worktree(sandbox: bool) -> None:
    parsed = json.loads(
        run_settings(state=[], hooks=None, sandbox=sandbox, kept=[], locks=[], keys=[])
    )
    assert {"Edit(./.claude/**)", "Write(./.claude/**)"} <= set(parsed["permissions"]["deny"])


def test_every_credential_the_run_environment_sets_is_denied_to_its_commands() -> None:
    receiver = Receiver("http://127.0.0.1:9", SecretBytes(b"\x02" * 32))
    set_by_the_board = telemetry_env(
        endpoint="http://localhost:4317",
        protocol=None,
        ticket_id="CF-1",
        run_id="r1",
        stage="build",
        repository="sample",
        receiver=receiver,
    )
    carrying_a_token = [name for name in set_by_the_board if name.endswith("_HEADERS")]
    assert carrying_a_token
    denied = [item["name"] for item in denied_variables([])]
    assert set(carrying_a_token) <= set(denied)
    assert MCP_TOKEN_VARIABLE in denied


# A run calls the board's own MCP tools (write_document, ...) all the time: asking the owner
# for each one parked every run in the Inbox.
@pytest.mark.parametrize("sandbox", [True, False])
def test_a_run_may_call_the_boards_own_mcp_tools_without_asking(sandbox: bool) -> None:
    settings = json.loads(
        run_settings(state=["/s"], hooks=None, sandbox=sandbox, kept=["/k"], locks=[], keys=[])
    )

    assert "mcp__code-factory" in settings["permissions"]["allow"]


def test_the_owners_standing_rules_stay_beside_the_boards_own_tools() -> None:
    hooks = {"permissions": {"allow": ["Bash(npm test)"]}}
    settings = json.loads(
        run_settings(state=["/s"], hooks=hooks, sandbox=False, kept=["/k"], locks=[], keys=[])
    )

    assert settings["permissions"]["allow"] == ["Bash(npm test)", "mcp__code-factory"]
