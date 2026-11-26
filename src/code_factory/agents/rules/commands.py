"""The runtime's command template."""

# `--tools` limits a claude run on a model served on this machine to the built-in tools a stage
# works with: the machine's other MCP servers and tools were most of a first request.
CLAUDE = (
    "claude -p {prompt} --permission-mode {permissions} --output-format stream-json --verbose "
    "{budget_flag} {settings_flag} {mcp_flag} {model_flag} {local_flags}"
)
# The launcher adds the isolated config, model and prompt to this non-interactive entry point.
CODEX = "codex exec"


def runtime_template(runtime: str) -> str:
    """A runtime's command template: codex's, else claude's."""
    return CODEX if runtime == "codex" else CLAUDE
