"""The hook JSON of a run's Claude Code settings, and its MCP configuration.

The commands are given as strings (the runs module decides what launches them); no output ever
holds a token value: the MCP server reads its token from the process environment.
"""

import json
from typing import Any

PERMISSION_TIMEOUT_S = 600
GUARD_TIMEOUT_S = 30
RECALL_SOURCES = "startup|resume|clear|compact"
SERVER = "code-factory"
MCP_TOKEN_VARIABLE = "CODE_FACTORY_MCP_TOKEN"  # noqa: S105  # a name, not a secret
# Only names the runtime accepts: an unknown one blocks interactive startup with a dialog.
HOOK_EVENTS = (
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "Notification",
    "SubagentStart",
    "SubagentStop",
    "Stop",
)
TOOL_RESULTS = ("PostToolUse", "PostToolUseFailure")

Settings = dict[str, Any]


def _carries(entry: object, command: str) -> bool:
    hooks = entry.get("hooks") if isinstance(entry, dict) else None
    return isinstance(hooks, list) and any(
        isinstance(hook, dict) and hook.get("command") == command for hook in hooks
    )


def _hooks_of(settings: Settings) -> dict[str, Any]:
    hooks = settings.get("hooks")
    return dict(hooks) if isinstance(hooks, dict) else {}


def _entries(hooks: dict[str, Any], event: str) -> list[Any]:
    entries = hooks.get(event)
    return list(entries) if isinstance(entries, list) else []


def with_permission_hook(rules: list[str], *, approval: bool, command: str) -> Settings | None:
    """The owner's standing rules and, unless off, the permission hook; None for neither."""
    settings: Settings = {}
    if rules:
        settings["permissions"] = {"allow": list(rules)}
    if approval:
        settings["hooks"] = {
            "PermissionRequest": [
                {
                    "hooks": [
                        {"type": "command", "command": command, "timeout": PERMISSION_TIMEOUT_S}
                    ]
                }
            ]
        }
    return settings or None


def with_tell_hook(settings: Settings, command: str) -> Settings:
    """`settings` with the hook that tells a run what was said on its ticket after a tool result."""
    out = dict(settings)
    hooks = _hooks_of(out)
    for event in TOOL_RESULTS:
        hooks[event] = [
            *_entries(hooks, event),
            {"hooks": [{"type": "command", "command": command}]},
        ]
    out["hooks"] = hooks
    return out


def with_capture_hooks(settings: Settings | None, capture: str, recall: str) -> Settings:
    """`settings` with the session capture hook on every event and the recall hook on start."""
    out = dict(settings or {})
    hooks = _hooks_of(out)
    wanted = [(event, "", capture) for event in HOOK_EVENTS] + [
        ("SessionStart", RECALL_SOURCES, recall)
    ]
    for event, matcher, command in wanted:
        entries = _entries(hooks, event)
        carrying = False
        for entry in entries:
            if _carries(entry, command):
                carrying = True
                if matcher and entry.get("matcher") != matcher:
                    entry["matcher"] = matcher
        if not carrying:
            entry = {"hooks": [{"type": "command", "command": command}]}
            if matcher:
                entry["matcher"] = matcher
            entries.append(entry)
        hooks[event] = entries
    out["hooks"] = hooks
    return out


def with_rewrite_guard(settings: Settings, guard: str) -> Settings:
    """`settings` with the guard run before every shell command; unchanged when it is there."""
    out = dict(settings)
    hooks = _hooks_of(out)
    entries = _entries(hooks, "PreToolUse")
    if any(_carries(entry, guard) for entry in entries):
        return settings
    entries.append(
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": guard, "timeout": GUARD_TIMEOUT_S}],
        }
    )
    hooks["PreToolUse"] = entries
    out["hooks"] = hooks
    return out


def mcp_config(command: str) -> str:
    """The `--mcp-config` JSON that starts the board's MCP server for a run.

    The token is an argument of the process list if it is written here, so only the name of the
    variable the server reads it from appears: `${CODE_FACTORY_MCP_TOKEN}`.
    """
    token = "${" + MCP_TOKEN_VARIABLE + "}"
    server = {"command": command, "args": ["mcp"], "env": {MCP_TOKEN_VARIABLE: token}}
    return json.dumps({"mcpServers": {SERVER: server}})


def mcp_http_config(url: str) -> str:
    """The `--mcp-config` JSON that reaches the board's MCP server at `url` over HTTP.

    The run's bearer token is named, `${CODE_FACTORY_MCP_TOKEN}`, never written: the runtime
    expands it from the run's environment. Over HTTP the server needs no database credential in
    the run's environment, as a stdio child of the run would.
    """
    token = "${" + MCP_TOKEN_VARIABLE + "}"
    server = {"type": "http", "url": url, "headers": {"Authorization": f"Bearer {token}"}}
    return json.dumps({"mcpServers": {SERVER: server}})
