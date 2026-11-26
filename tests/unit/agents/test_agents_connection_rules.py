"""Connection rules: the addresses and key variables the previous implementation took and
refused (`connections.rs` tests), with its sentences."""

import pytest

from code_factory.agents.models.agents import AgentDefinition
from code_factory.agents.models.connections import ConnectionChange, ConnectionDefinition
from code_factory.agents.rules.connections import (
    KINDS,
    agent_refusal,
    apply_connection_change,
    codex_takes,
    kind_of,
    models_address,
    needs_broker,
    runs_here,
    unbilled,
)
from code_factory.platform.errors import BadRequestError

CHARACTERS = (
    "an address is http:// or https://, a host, a port and a path of letters, digits, "
    "'.', '_', '-' and '/'"
)


def local(kind: str) -> str:
    return f"{kind} connections run on this machine: the address's host is localhost or 127.0.0.1"


KEY = {"anthropic": "ANTHROPIC_API_KEY", "openrouter": "OPENROUTER_API_KEY"}


def made(
    kind: str, base_url: str = "", key_env: str | None = None, name: str = "c", **more: str
) -> ConnectionDefinition:
    key = KEY.get(kind, "") if key_env is None else key_env
    change = ConnectionChange(name=name, kind=kind, base_url=base_url, key_env=key, **more)
    return apply_connection_change(
        ConnectionDefinition(name="", kind="custom", base_url="", key_env=""), change
    )


def refusal(*args: str, **kwargs: str) -> str:
    with pytest.raises(BadRequestError) as caught:
        made(*args, **kwargs)
    return str(caught.value)


def test_there_are_seven_kinds_in_the_order_the_page_offers_them() -> None:
    assert [(k.kind, k.label, k.base_url, k.key) for k in KINDS] == [
        ("anthropic", "Anthropic", "https://api.anthropic.com", "required"),
        ("openrouter", "OpenRouter", "https://openrouter.ai/api", "required"),
        ("codex-login", "Codex login (ChatGPT)", "https://chatgpt.com/backend-api/codex", "login"),
        ("lm-studio", "LM Studio", "http://localhost:1234", "none"),
        ("ollama", "Ollama", "http://localhost:11434", "none"),
        ("llama-cpp", "llama.cpp", "http://localhost:8080", "none"),
        ("custom", "Custom", "", "none"),
    ]
    studio = kind_of("lm-studio")
    assert studio is not None
    assert studio.wire() == {
        "kind": "lm-studio",
        "label": "LM Studio",
        "base_url": "http://localhost:1234",
        "key": "none",
    }
    assert kind_of("nope") is None


@pytest.mark.parametrize(
    ("kind", "base_url"),
    [
        ("anthropic", ""),
        ("anthropic", "https://api.anthropic.com"),
        ("openrouter", "https://openrouter.ai/api/"),
        ("lm-studio", "http://127.0.0.1:5000"),
        ("ollama", "http://localhost:11434"),
        ("llama-cpp", ""),
        ("custom", "http://127.0.0.1:4000/gateway"),
        ("codex-login", ""),
    ],
)
def test_an_address_its_kind_is_for_is_taken(kind: str, base_url: str) -> None:
    assert made(kind, base_url).kind == kind


def test_an_address_is_defaulted_and_loses_its_trailing_slash() -> None:
    assert made("ollama", "").base_url == "http://localhost:11434"
    assert (
        made("custom", "http://127.0.0.1:4000/gateway/").base_url == "http://127.0.0.1:4000/gateway"
    )


@pytest.mark.parametrize(
    ("kind", "base_url", "key", "why"),
    [
        (
            "custom",
            "http://169.254.169.254",
            "",
            local("custom"),
        ),
        (
            "lm-studio",
            "http://10.0.0.5:1234",
            "",
            local("lm-studio"),
        ),
        (
            "ollama",
            "http://localhost.evil.example",
            "",
            local("ollama"),
        ),
        (
            "anthropic",
            "https://api.anthropic.com.evil.example",
            "ANTHROPIC_API_KEY",
            "anthropic connections go to https://api.anthropic.com",
        ),
        (
            "anthropic",
            "http://api.anthropic.com",
            "ANTHROPIC_API_KEY",
            "anthropic connections go to https://api.anthropic.com",
        ),
        (
            "anthropic",
            "https://api.anthropic.com:8443",
            "ANTHROPIC_API_KEY",
            "anthropic connections go to https://api.anthropic.com",
        ),
        (
            "anthropic",
            "https://openrouter.ai/api",
            "ANTHROPIC_API_KEY",
            "anthropic connections go to https://api.anthropic.com",
        ),
        (
            "openrouter",
            "https://api.openrouter.ai/api",
            "OPENROUTER_API_KEY",
            "openrouter connections go to https://openrouter.ai",
        ),
        ("ollama", "ftp://localhost", "", "an address is http:// or https:// and a host"),
    ],
)
def test_an_address_for_another_host_is_refused_with_the_host_its_kind_is_for(
    kind: str, base_url: str, key: str, why: str
) -> None:
    assert refusal(kind, base_url, key) == why


@pytest.mark.parametrize(
    ("kind", "base_url", "why"),
    [
        ("anthropic", r"https://api.anthropic.com\@evil.example", CHARACTERS),
        ("anthropic", "https://api.anthropic.com@evil.example", CHARACTERS),
        ("anthropic", "https://evil.example#@api.anthropic.com", CHARACTERS),
        ("anthropic", "https://api.anthropic.com?x=1", CHARACTERS),
        ("openrouter", "https://user:pw@openrouter.ai/api", CHARACTERS),
        ("ollama", "http://127.0.0.1@evil.example", CHARACTERS),
        ("custom", "http://[::ffff:a9fe:a9fe]", CHARACTERS),
        ("lm-studio", "http://localhost:1234/%2e%2e", CHARACTERS),
        (
            "anthropic",
            "HTTPS://API.ANTHROPIC.COM",
            "write the address as https://api.anthropic.com",
        ),
        ("lm-studio", "http://localhost:01234", "write the address as http://localhost:1234"),
        ("custom", "http://127.0.0.1:4000/a/../b", "write the address as http://127.0.0.1:4000/b"),
        ("custom", "http://127.1:4000", "write the address as http://127.0.0.1:4000"),
        ("anthropic", "https://api.anthropic.com/v2", "anthropic connections take no path"),
        (
            "openrouter",
            "https://openrouter.ai/other",
            "openrouter connections take no path but /api",
        ),
        ("lm-studio", "http://localhost:1234/v1", "lm-studio connections take no path"),
        (
            "codex-login",
            "https://chatgpt.com/other",
            "codex-login connections take no path but /backend-api/codex",
        ),
    ],
)
def test_an_address_a_parser_could_read_as_another_host_is_refused(
    kind: str, base_url: str, why: str
) -> None:
    assert refusal(kind, base_url) == why


@pytest.mark.parametrize(
    ("kind", "base_url", "models"),
    [
        ("anthropic", "https://api.anthropic.com", "https://api.anthropic.com/v1/models"),
        ("openrouter", "https://openrouter.ai/api", "https://openrouter.ai/api/v1/models"),
        ("lm-studio", "http://localhost:1234", "http://localhost:1234/api/v0/models"),
        ("custom", "http://127.0.0.1:4000/gateway", "http://127.0.0.1:4000/gateway/v1/models"),
    ],
)
def test_the_models_are_listed_at_the_address_with_its_path_appended(
    kind: str, base_url: str, models: str
) -> None:
    assert models_address(made(kind, base_url)) == models


def test_a_custom_connection_needs_an_address() -> None:
    assert refusal("custom", "  ") == "a custom connection needs an address"


def test_an_unknown_kind_lists_the_seven() -> None:
    assert refusal("nope") == (
        "unknown kind nope: anthropic, openrouter, codex-login, lm-studio, ollama, llama-cpp, "
        "custom"
    )


KEY_RULE = (
    "an anthropic key variable is ANTHROPIC_..._API_KEY and an openrouter one "
    "OPENROUTER_..._API_KEY, in capitals"
)


@pytest.mark.parametrize("name", ["OPENROUTER_API_KEY", "OPENROUTER_WORK_API_KEY"])
def test_an_openrouter_connection_reads_a_key_variable_of_its_provider(name: str) -> None:
    assert made("openrouter", "", name).key_env == name


@pytest.mark.parametrize(
    "name",
    [
        "ANTHROPIC_API_KEY",
        "MY_GATEWAY_AUTH_TOKEN",
        "TEAM_TOKEN",
        "HOME",
        "GITHUB_TOKEN",
        "AWS_BEDROCK_API_KEY",
        "openrouter_api_key",
        "1_API_KEY",
        "_API_KEY",
        "API_KEY",
        "OPENROUTER_API_KEY_FILE",
        "OPENROUTER_API_KEY\n",
    ],
)
def test_a_name_that_is_not_the_providers_api_key_is_refused(name: str) -> None:
    assert refusal("openrouter", "", name) == KEY_RULE


def test_anthropic_reads_only_its_own_api_key() -> None:
    assert made("anthropic", "", "ANTHROPIC_WORK_API_KEY").key_env == "ANTHROPIC_WORK_API_KEY"
    for name in (
        "VAULT_TOKEN",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "OPENROUTER_API_KEY",
    ):
        assert refusal("anthropic", "", name) == KEY_RULE


def test_a_keyed_kind_without_a_key_name_is_refused() -> None:
    assert (
        refusal("anthropic", "", "") == "anthropic connections read their key from a key variable"
    )


@pytest.mark.parametrize("kind", ["lm-studio", "custom", "codex-login"])
def test_a_kind_that_sends_no_key_carries_none(kind: str) -> None:
    base_url = "http://127.0.0.1:4000" if kind == "custom" else ""
    assert refusal(kind, base_url, "X_API_KEY") == (
        f"{kind} connections carry no key: keys go only to https://api.anthropic.com "
        "and https://openrouter.ai"
    )


MANAGEMENT = (
    "only an openrouter connection names a management key variable, "
    "OPENROUTER_..._API_KEY in capitals and not its own key variable"
)


def test_a_management_key_is_for_openrouter_a_key_variable_and_not_its_own() -> None:
    ok = made("openrouter", "", "OPENROUTER_API_KEY", management_key_env="OPENROUTER_MGMT_API_KEY")
    assert ok.management_key_env == "OPENROUTER_MGMT_API_KEY"
    assert (
        refusal("openrouter", "", "OPENROUTER_API_KEY", management_key_env="OPENROUTER_API_KEY")
        == MANAGEMENT
    )
    assert refusal("openrouter", "", "OPENROUTER_API_KEY", management_key_env="HOME") == MANAGEMENT
    assert (
        refusal("anthropic", "", "ANTHROPIC_API_KEY", management_key_env="OPENROUTER_X_API_KEY")
        == MANAGEMENT
    )


def test_the_kind_predicates_follow_where_a_run_is_served() -> None:
    def connection(kind: str) -> ConnectionDefinition:
        return ConnectionDefinition(name="c", kind=kind, base_url="", key_env="")

    for local in ("lm-studio", "ollama", "llama-cpp", "custom"):
        assert runs_here(connection(local))
        assert unbilled(connection(local))
        assert codex_takes(connection(local))
    for hosted in ("anthropic", "openrouter", "codex-login", "unknown"):
        assert not runs_here(connection(hosted))
    assert codex_takes(connection("openrouter"))
    assert codex_takes(connection("codex-login"))
    assert not codex_takes(connection("anthropic"))
    assert unbilled(connection("codex-login"))
    assert not unbilled(connection("openrouter"))
    assert needs_broker(connection("codex-login"))
    assert needs_broker(
        ConnectionDefinition(name="c", kind="openrouter", base_url="", key_env="OPENROUTER_API_KEY")
    )
    assert not needs_broker(connection("ollama"))


CODEX_ONLY = (
    "a codex-login connection serves only a codex agent: it is the owner's ChatGPT login, "
    "which no other runtime speaks"
)
CODEX_REFUSAL = (
    "a codex run starts only with a connection served on this machine "
    "(lm-studio, ollama, llama-cpp or custom), an openrouter connection or a codex-login connection"
)


def agent(runtime: str, connection: str = "") -> AgentDefinition:
    return AgentDefinition(name="a", runtime=runtime, connection=connection)


def test_a_claude_agent_takes_no_connection_or_any_but_the_codex_login() -> None:
    kept = [
        made("ollama", name="local"),
        made("anthropic", name="cloud"),
        made("codex-login", name="login"),
    ]
    assert agent_refusal(agent("claude"), kept) is None
    assert agent_refusal(agent("claude", "local"), kept) is None
    assert agent_refusal(agent("claude", "cloud"), kept) is None
    assert agent_refusal(agent("claude", "login"), kept) == CODEX_ONLY
    assert agent_refusal(agent("claude", "gone"), kept) == "no connection named gone"


def test_a_codex_agent_takes_a_local_openrouter_or_login_connection_only() -> None:
    kept = [
        made("ollama", name="local"),
        made("openrouter", name="router"),
        made("codex-login", name="login"),
        made("anthropic", name="cloud"),
    ]
    assert agent_refusal(agent("codex", "local"), kept) is None
    assert agent_refusal(agent("codex", "router"), kept) is None
    assert agent_refusal(agent("codex", "login"), kept) is None
    assert agent_refusal(agent("codex", "cloud"), kept) == CODEX_REFUSAL
    assert agent_refusal(agent("codex"), kept) == CODEX_REFUSAL
