"""What a connection gives a run of an agent: its environment variables and codex config.

Key values are `SecretStr` and a key variable that holds nothing refuses the run; the config text
never holds a key.
"""

from pydantic import SecretStr

from code_factory.agents.models.connections import ConnectionDefinition, ConnectionKind
from code_factory.agents.models.constants import CODEX_LOGIN
from code_factory.agents.rules.connections import Address, address, rules, runs_here
from code_factory.platform.errors import BadRequestError, ConflictError

# The variable a keyed codex run's token from the key broker is in: a name of the board's own, so
# an owner's OPENAI_API_KEY is never taken for it.
CODEX_TOKEN = "CODE_FACTORY_CODEX_TOKEN"  # noqa: S105  # a name, not a secret
CODEX_PROVIDER = "board"

# A run's variables: each set to a value or, when None, removed.
Variables = dict[str, SecretStr | None]


def _parts(
    connection: ConnectionDefinition, key: SecretStr | None
) -> tuple[ConnectionKind, SecretStr | None, Address]:
    """The kind, key and address a run on `connection` is given, else why it may not start."""
    try:
        kind = rules(connection)
        where = address(connection)
    except BadRequestError as why:
        msg = f"connection {connection.name}: {why}"
        raise BadRequestError(msg) from None
    if connection.key_env and (key is None or not key.get_secret_value()):
        msg = (
            f"connection {connection.name} reads its key from {connection.key_env}, "
            "which is not set in the board's environment"
        )
        raise ConflictError(msg)
    return kind, key if connection.key_env else None, where


def _base(where: Address) -> str:
    return where.with_path("").rstrip("/")


def run_environment(
    connection: ConnectionDefinition, model: str, key: SecretStr | None
) -> Variables:
    """The variables a claude run on `connection` gets.

    Anthropic's key goes as the API key, every other kind's as the bearer token with the API key
    empty, so the owner's own Anthropic key never reaches another host. A server on this machine
    also gets the two settings that stop claude sending `output_config` and `thinking`.
    """
    kind, given, where = _parts(connection, key)
    env: Variables = {"ANTHROPIC_BASE_URL": SecretStr(_base(where))}
    if connection.kind == "anthropic":
        env["ANTHROPIC_API_KEY"] = given
        env["ANTHROPIC_AUTH_TOKEN"] = None
    else:
        env["ANTHROPIC_AUTH_TOKEN"] = given or SecretStr(kind.token)
        env["ANTHROPIC_API_KEY"] = SecretStr("")
    if model:
        env["ANTHROPIC_MODEL"] = SecretStr(model)
    if runs_here(connection):
        env["CLAUDE_CODE_EFFORT_LEVEL"] = SecretStr("auto")
        env["CLAUDE_CODE_DISABLE_THINKING"] = SecretStr("1")
    return env


def _openai_address(where: Address) -> str:
    """Where an OpenAI-compatible server answers: `<base>/v1`, or the base when it has a path."""
    base = _base(where)
    return base if where.path.rstrip("/") else f"{base}/v1"


def _quoted(text: str) -> str:
    """A TOML basic string: backslash, quote and control characters escaped."""
    out = []
    for char in text:
        if char in '"\\':
            out.append("\\" + char)
        elif ord(char) < 0x20 or ord(char) == 0x7F:  # noqa: PLR2004
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def codex_untrusted(project: str) -> str:
    """The table a codex run's config ends with, marking `project` untrusted.

    codex then reads no `.codex/config.toml` of the repository, whose features and MCP servers it
    would otherwise apply.
    """
    return f'[projects.{_quoted(project)}]\ntrust_level = "untrusted"\n'


def codex_config(
    connection: ConnectionDefinition, model: str, key: SecretStr | None, broker: int | None
) -> tuple[str, str]:
    """The config.toml a codex run reads from its codex folder, and the model as codex names it.

    One provider at the connection's OpenAI-compatible address with no key (its server checks
    none), or, through the key broker on `broker`'s port, sent the run's token from
    `CODEX_TOKEN`; no update check, analytics or web search. `key` is only checked to be set: it
    is never written. Keys are sorted as the previous layout wrote them.
    """
    kind, _, where = _parts(connection, key)
    name = f"name = {_quoted(kind.label)}"
    if broker is not None:
        provider = [
            f"base_url = {_quoted(f'http://127.0.0.1:{broker}/v1')}",
            f"env_key = {_quoted(CODEX_TOKEN)}",
            name,
        ]
    elif connection.kind == CODEX_LOGIN:
        msg = "a codex-login connection is reached only through the key broker"
        raise ConflictError(msg)
    elif connection.key_env:
        msg = (
            f"connection {connection.name} holds a key, so a codex run reaches it only through "
            "the key broker"
        )
        raise ConflictError(msg)
    else:
        provider = [f"base_url = {_quoted(_openai_address(where))}", name]
    # Without default_mode_request_user_input codex tells the model its question tool is
    # unavailable in the default mode; a login shell would reorder the board's pinned PATH.
    lines = [
        "allow_login_shell = false",
        "check_for_update_on_startup = false",
        f"model_provider = {_quoted(CODEX_PROVIDER)}",
        'web_search = "disabled"',
        "",
        "[analytics]",
        "enabled = false",
        "",
        "[features]",
        "default_mode_request_user_input = true",
        "",
        f"[model_providers.{CODEX_PROVIDER}]",
        *provider,
        "",
    ]
    return "\n".join(lines), model
