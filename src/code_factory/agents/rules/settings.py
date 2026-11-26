"""Claude Code's `--settings` JSON for a run: its hooks, its sandbox and what it is denied."""

import json
from typing import Any

from code_factory.agents.models.constants import SECRET_FILES, SECRET_VARIABLES
from code_factory.agents.rules.hooks import MCP_TOKEN_VARIABLE, SERVER

# A run that wrote its worktree's `.claude` folder would have Claude Code's hooks there read as
# its own on a later start.
# A Claude Code allow rule naming an MCP server covers every tool it serves.
OWN_TOOLS = f"mcp__{SERVER}"
WORKTREE_CLAUDE = ("Edit(./.claude/**)", "Write(./.claude/**)")
RUNTIME_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")
# The credentials the board puts into a run's own environment: the MCP server's token and the
# header that carries the run's telemetry token (and its general form, which a repository's
# endpoint may set).
BOARD_VARIABLES = (
    MCP_TOKEN_VARIABLE,
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_EXPORTER_OTLP_LOGS_HEADERS",
)


def denied_files(state: list[str], kept: list[str]) -> list[str]:
    """The permission rules that deny the file tools every secret and the state folder.

    Each secret is denied for reading, the state folder for reading and editing, and every path
    in `kept` for editing; an absolute path is written with a leading `/`.
    """
    rules = [rule for path in SECRET_FILES for rule in (f"Read({path})", f"Read({path}/**)")]
    rules += WORKTREE_CLAUDE
    for path in state:
        for tool in ("Read", "Edit"):
            rules += [f"{tool}(/{path})", f"{tool}(/{path}/**)"]
    for path in kept:
        rules += [f"Edit(/{path})", f"Edit(/{path}/**)"]
    return rules


def denied_variables(keys: list[str]) -> list[dict[str, str]]:
    """The variables a run's commands are denied.

    The secrets, the board's own credentials, the runtime's keys and `keys`.
    """
    names = [*SECRET_VARIABLES, *RUNTIME_VARIABLES, *BOARD_VARIABLES, *keys]
    return [{"name": name, "mode": "deny"} for name in names]


def sandbox_settings(
    state: list[str], kept: list[str], locks: list[str], keys: list[str]
) -> dict[str, Any]:
    """The sandbox block: commands reach no host, no secret, and write only what is allowed."""
    return {
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "allowUnsandboxedCommands": False,
            "network": {"allowedDomains": [], "strictAllowlist": True, "allowLocalBinding": False},
            "filesystem": {"denyRead": state, "allowWrite": locks, "denyWrite": [*state, *kept]},
            "credentials": {
                "files": [{"path": path, "mode": "deny"} for path in SECRET_FILES],
                "envVars": denied_variables(keys),
            },
        }
    }


def run_settings(  # noqa: PLR0913  # the inputs of one run's settings, named
    *,
    state: list[str],
    hooks: dict[str, Any] | None,
    sandbox: bool,
    kept: list[str],
    locks: list[str],
    keys: list[str],
) -> str:
    """The `--settings` JSON text: hooks, sandbox (unless off), and the denied files.

    Turning the sandbox off drops its block and keeps the denies.
    """
    settings = dict(hooks or {})
    permissions = settings.get("permissions")
    permissions = dict(permissions) if isinstance(permissions, dict) else {}
    if sandbox:
        settings.update(sandbox_settings(state, kept, locks, keys))
    permissions["deny"] = denied_files(state, kept)
    # The board's own MCP tools (write_document, ...) never wait on the owner.
    allowed = [rule for rule in permissions.get("allow", []) if rule != OWN_TOOLS]
    permissions["allow"] = [*allowed, OWN_TOOLS]
    settings["permissions"] = permissions
    return json.dumps(settings)
