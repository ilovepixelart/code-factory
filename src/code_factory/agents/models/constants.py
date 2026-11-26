"""The runtimes, columns, kinds and secret lists the module and its neighbours share."""

from typing import get_args

from code_factory.tickets.models import TicketType

RUNTIMES = ("claude", "codex")
ROLES = ("spec", "build", "review")
TICKET_TYPES = tuple(str(kind) for kind in get_args(TicketType))
KIND_NAMES = (
    "anthropic",
    "openrouter",
    "codex-login",
    "lm-studio",
    "ollama",
    "llama-cpp",
    "custom",
)
CODEX_LOGIN = "codex-login"
NAME_LIMIT = 40
CONTEXT_LIMIT = 8000
CONTEXT_VERSIONS = 20
CONTEXT_FLOOR = 64_000
ANTHROPIC_VERSION = "2023-06-01"

# Every secret a run is denied, `~/` read as the home folder. The settings module keeps the same
# list for its container mount check; a test in each compares it with this one.
SECRET_FILES = (
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.config/gh",
    "~/.docker/config.json",
    "~/.netrc",
    "~/.npmrc",
    "~/.pypirc",
    "~/.git-credentials",
    "~/.omp",
    "~/.local/share/opencode/auth.json",
    "~/.kube",
    "~/.azure",
    "~/.pi/agent",
    "~/.codex",
    "~/.claude",
    "~/.claude.json",
)

# Credentials of other tools a run is denied and a connection may not read its key from.
SECRET_VARIABLES = (
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "NPM_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)

GUARANTEES = (
    "contained in a sandbox",
    "permission requests reach the Inbox",
    "the memory store reaches it",
    "none of the owner's hooks, plugins or MCP servers run",
)
