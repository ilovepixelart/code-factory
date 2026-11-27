"""The connection kinds, their addresses and key names, and which agent may use which."""

import re
from dataclasses import dataclass

from ada_url import URL

from code_factory.agents.models.agents import AgentDefinition
from code_factory.agents.models.connections import (
    ConnectionChange,
    ConnectionDefinition,
    ConnectionKind,
)
from code_factory.agents.models.constants import CODEX_LOGIN, KIND_NAMES, SECRET_VARIABLES
from code_factory.agents.rules.names import check_name
from code_factory.platform.errors import BadRequestError

KINDS = (
    ConnectionKind(
        "anthropic", "Anthropic", "https://api.anthropic.com", "required", "api.anthropic.com"
    ),
    ConnectionKind(
        "openrouter", "OpenRouter", "https://openrouter.ai/api", "required", "openrouter.ai"
    ),
    ConnectionKind(
        CODEX_LOGIN,
        "Codex login (ChatGPT)",
        "https://chatgpt.com/backend-api/codex",
        "login",
        "chatgpt.com",
    ),
    ConnectionKind("lm-studio", "LM Studio", "http://localhost:1234", "none", "", "lmstudio"),
    ConnectionKind("ollama", "Ollama", "http://localhost:11434", "none", "", "ollama"),
    ConnectionKind("llama-cpp", "llama.cpp", "http://localhost:8080", "none", "", "llama-cpp"),
    ConnectionKind("custom", "Custom", "", "none", "", "custom"),
)

CHARACTERS = (
    "an address is http:// or https://, a host, a port and a path of letters, digits, "
    "'.', '_', '-' and '/'"
)
KEY_RULE = (
    "an anthropic key variable is ANTHROPIC_..._API_KEY and an openrouter one "
    "OPENROUTER_..._API_KEY, in capitals"
)
MANAGEMENT_RULE = (
    "only an openrouter connection names a management key variable, "
    "OPENROUTER_..._API_KEY in capitals and not its own key variable"
)
CODEX_LOGIN_ONLY = (
    "a codex-login connection serves only a codex agent: it is the owner's ChatGPT login, "
    "which no other runtime speaks"
)
CODEX_REFUSAL = (
    "a codex run starts only with a connection served on this machine "
    "(lm-studio, ollama, llama-cpp or custom), an openrouter connection or a codex-login connection"
)
_KEY_VARIABLE = re.compile(r"[A-Z][A-Z0-9_]*API_KEY")
_KEY_PREFIX = {"anthropic": "ANTHROPIC_", "openrouter": "OPENROUTER_"}
_THIS_MACHINE = ("localhost", "127.0.0.1")


def kind_of(kind: str) -> ConnectionKind | None:
    """The kind named `kind`."""
    return next((known for known in KINDS if known.kind == kind), None)


def runs_here(connection: ConnectionDefinition) -> bool:
    """Whether the connection's kind is served on this machine, where a run costs nothing."""
    known = kind_of(connection.kind)
    return known is not None and not known.host


def codex_takes(connection: ConnectionDefinition) -> bool:
    """Whether a codex run starts on the connection.

    A local one, an openrouter one or the owner's codex login: anthropic serves no Responses API.
    """
    return runs_here(connection) or connection.kind in ("openrouter", CODEX_LOGIN)


def needs_broker(connection: ConnectionDefinition) -> bool:
    """Whether a codex run on the connection goes through the key broker: keyed, or the login."""
    return bool(connection.key_env) or connection.kind == CODEX_LOGIN


def unbilled(connection: ConnectionDefinition) -> bool:
    """Whether a run on the connection costs nothing per token: local, or the codex login."""
    return runs_here(connection) or connection.kind == CODEX_LOGIN


@dataclass(frozen=True)
class Address:
    """A parsed connection address: the parts every request is built from, never the text."""

    scheme: str
    host: str
    port: str
    path: str

    def with_path(self, path: str) -> str:
        """The address with `path` appended after its own path."""
        port = f":{self.port}" if self.port else ""
        base = self.path.rstrip("/")
        return f"{self.scheme}://{self.host}{port}{base}/{path.strip('/')}"


def plain_address(text: str) -> Address:
    """The address when it is written in the one plain form every parser reads alike.

    Only letters, digits and `:/._-` (no user, query, fragment, escape or backslash); exactly what
    it parses to; http or https with a host.
    """
    if not all(char.isascii() and (char.isalnum() or char in ":/._-") for char in text):
        raise BadRequestError(CHARACTERS)
    try:
        parsed = URL(text)
    except ValueError:
        raise BadRequestError(CHARACTERS) from None
    plain = parsed.href.rstrip("/")
    if plain != text.rstrip("/"):
        msg = f"write the address as {plain}"
        raise BadRequestError(msg)
    scheme = parsed.protocol.removesuffix(":")
    if scheme not in ("http", "https") or not parsed.hostname:
        msg = "an address is http:// or https:// and a host"
        raise BadRequestError(msg)
    return Address(scheme, parsed.hostname, parsed.port, parsed.pathname)


_PATHS = {"openrouter": ("", "/api"), CODEX_LOGIN: ("/backend-api/codex",), "custom": None}


def _path_refusal(kind: ConnectionKind, path: str) -> str | None:
    """Why the path does not suit the kind; a custom address may carry any."""
    path = path.rstrip("/")
    if kind.kind not in _PATHS:
        return f"{kind.kind} connections take no path" if path else None
    allowed = _PATHS[kind.kind]
    if allowed is None or path in allowed:
        return None
    return f"{kind.kind} connections take no path but {allowed[-1]}"


def address(connection: ConnectionDefinition) -> Address:
    """The connection's address, parsed, else why it is not taken.

    A keyed kind is exactly `https://<its host>` on the default port; any other is on this
    machine; no path but what the kind needs.
    """
    kind = kind_of(connection.kind)
    if kind is None:
        msg = f"unknown kind {connection.kind}: {', '.join(KIND_NAMES)}"
        raise BadRequestError(msg)
    parsed = plain_address(connection.base_url)
    if not kind.host:
        if parsed.host not in _THIS_MACHINE:
            msg = (
                f"{kind.kind} connections run on this machine: "
                "the address's host is localhost or 127.0.0.1"
            )
            raise BadRequestError(msg)
    elif parsed.scheme != "https" or parsed.host != kind.host or parsed.port:
        msg = f"{kind.kind} connections go to https://{kind.host}"
        raise BadRequestError(msg)
    if (why := _path_refusal(kind, parsed.path)) is not None:
        raise BadRequestError(why)
    return parsed


def _is_key_variable(kind: str, name: str) -> bool:
    prefix = _KEY_PREFIX.get(kind)
    return (
        prefix is not None
        and _KEY_VARIABLE.fullmatch(name) is not None
        and name.startswith(prefix)
        and name not in SECRET_VARIABLES
    )


def rules(connection: ConnectionDefinition) -> ConnectionKind:
    """The kind of a connection that keeps the rules, else why not.

    Its address is taken; a keyed kind reads its key from a key variable of its provider, any
    other reads none. Every add, change, check and run holds a connection to these rules.
    """
    address(connection)
    kind = kind_of(connection.kind)
    assert kind is not None  # noqa: S101  # `address` refused an unknown kind
    management = connection.management_key_env
    if management is not None and (
        kind.kind != "openrouter"
        or not _is_key_variable(kind.kind, management)
        or management == connection.key_env
    ):
        raise BadRequestError(MANAGEMENT_RULE)
    if kind.key != "required":
        if connection.key_env:
            msg = (
                f"{kind.kind} connections carry no key: keys go only to "
                "https://api.anthropic.com and https://openrouter.ai"
            )
            raise BadRequestError(msg)
        return kind
    if not connection.key_env:
        msg = f"{kind.kind} connections read their key from a key variable"
        raise BadRequestError(msg)
    if not _is_key_variable(kind.kind, connection.key_env):
        raise BadRequestError(KEY_RULE)
    return kind


def apply_connection_change(
    connection: ConnectionDefinition, change: ConnectionChange
) -> ConnectionDefinition:
    """`connection` with the change applied, its address defaulted and without a trailing `/`."""
    fields = change.model_dump(exclude_none=True)
    management = fields.pop("management_key_env", None)
    merged = connection.model_copy(update=fields)
    if management is not None:
        merged = merged.model_copy(update={"management_key_env": management or None})
    check_name(merged.name)
    base_url = merged.base_url.strip().rstrip("/")
    if not base_url:
        known = kind_of(merged.kind)
        base_url = known.base_url if known else ""
    if not base_url and merged.kind == "custom":
        msg = "a custom connection needs an address"
        raise BadRequestError(msg)
    merged = merged.model_copy(update={"base_url": base_url})
    rules(merged)
    return merged


def agent_refusal(agent: AgentDefinition, connections: list[ConnectionDefinition]) -> str | None:
    """Why an agent may not be defined with its connection; None when it may."""
    codex = agent.runtime == "codex"
    if not agent.connection:
        return CODEX_REFUSAL if codex else None
    connection = next((c for c in connections if c.name == agent.connection), None)
    if connection is None:
        return f"no connection named {agent.connection}"
    if connection.kind == CODEX_LOGIN and not codex:
        return CODEX_LOGIN_ONLY
    return CODEX_REFUSAL if codex and not codex_takes(connection) else None


def models_address(connection: ConnectionDefinition) -> str:
    """Where a connection lists its models: its address with the list's path appended."""
    path = "/api/v0/models" if connection.kind == "lm-studio" else "/v1/models"
    return address(connection).with_path(path)
