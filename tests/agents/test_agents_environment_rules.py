"""What a connection gives a run (environment, codex config) and the codex login file, against
the previous implementation's cases and its two `auth.json` goldens."""

import tomllib
from pathlib import Path

import pytest
from pydantic import SecretStr

from code_factory.agents.models.connections import ConnectionDefinition, Status
from code_factory.agents.rules.environment import (
    CODEX_TOKEN,
    codex_config,
    codex_untrusted,
    run_environment,
)
from code_factory.agents.rules.login import codex_login, login_reach, login_status
from code_factory.platform.errors import BadRequestError, ConflictError

GOLDEN = Path(__file__).parent.parent / "golden" / "agents"
KEY = SecretStr("sk-or-1")


def conn(name: str, kind: str, base_url: str, key_env: str = "") -> ConnectionDefinition:
    return ConnectionDefinition(name=name, kind=kind, base_url=base_url, key_env=key_env)


def revealed(env: dict[str, SecretStr | None]) -> dict[str, str | None]:
    return {k: None if v is None else v.get_secret_value() for k, v in env.items()}


def test_openrouter_gives_its_key_as_the_bearer_token_and_an_empty_api_key() -> None:
    cloud = conn("cloud", "openrouter", "https://openrouter.ai/api", "OPENROUTER_API_KEY")
    assert revealed(run_environment(cloud, "m-1", KEY)) == {
        "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_AUTH_TOKEN": "sk-or-1",
        "ANTHROPIC_MODEL": "m-1",
    }


def test_anthropic_gives_its_key_as_the_api_key_and_removes_the_token() -> None:
    direct = conn("direct", "anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY")
    assert revealed(run_environment(direct, "m-1", KEY)) == {
        "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
        "ANTHROPIC_API_KEY": "sk-or-1",
        "ANTHROPIC_AUTH_TOKEN": None,
        "ANTHROPIC_MODEL": "m-1",
    }


def test_a_local_server_gets_its_placeholder_token_and_the_two_settings_that_stop_thinking() -> (
    None
):
    assert revealed(run_environment(conn("o", "ollama", "http://localhost:11434"), "", None)) == {
        "ANTHROPIC_BASE_URL": "http://localhost:11434",
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_AUTH_TOKEN": "ollama",
        "CLAUDE_CODE_EFFORT_LEVEL": "auto",
        "CLAUDE_CODE_DISABLE_THINKING": "1",
    }
    for kind, token in (("llama-cpp", "llama-cpp"), ("lm-studio", "lmstudio")):
        env = run_environment(conn("c", kind, "http://localhost:5000"), "", None)
        assert env["ANTHROPIC_AUTH_TOKEN"] == SecretStr(token)


def test_a_key_variable_that_holds_nothing_refuses_the_run_without_naming_a_value() -> None:
    missing = conn("cloud", "openrouter", "https://openrouter.ai/api", "OPENROUTER_SPARE_API_KEY")
    for key in (None, SecretStr("")):
        with pytest.raises(ConflictError) as caught:
            run_environment(missing, "m-1", key)
        assert str(caught.value) == (
            "connection cloud reads its key from OPENROUTER_SPARE_API_KEY, "
            "which is not set in the board's environment"
        )


def test_the_environment_never_shows_a_key_in_its_repr() -> None:
    cloud = conn("cloud", "openrouter", "https://openrouter.ai/api", "OPENROUTER_API_KEY")
    assert "sk-or-1" not in repr(run_environment(cloud, "m", KEY))


def test_a_connection_that_breaks_the_rules_gives_no_environment() -> None:
    given = conn("c", "ollama", "http://10.0.0.5:11434")
    with pytest.raises(BadRequestError):
        run_environment(given, "", None)


def test_a_codex_config_names_one_provider_without_a_key_and_the_board_options() -> None:
    text, selector = codex_config(conn("o", "ollama", "http://localhost:11434"), "qwen", None, None)
    assert selector == "qwen"
    assert tomllib.loads(text) == {
        "allow_login_shell": False,
        "analytics": {"enabled": False},
        "check_for_update_on_startup": False,
        "features": {"default_mode_request_user_input": True},
        "model_provider": "board",
        "model_providers": {"board": {"name": "Ollama", "base_url": "http://localhost:11434/v1"}},
        "web_search": "disabled",
    }


def test_a_codex_config_keeps_the_path_of_a_custom_address() -> None:
    text, _ = codex_config(conn("g", "custom", "http://127.0.0.1:4000/gateway"), "m", None, None)
    assert tomllib.loads(text)["model_providers"]["board"]["base_url"] == (
        "http://127.0.0.1:4000/gateway"
    )


def test_a_keyed_codex_run_goes_to_the_broker_and_reads_its_token_from_the_board_variable() -> None:
    router = conn("r", "openrouter", "https://openrouter.ai/api", "OPENROUTER_API_KEY")
    text, _ = codex_config(router, "m", KEY, 4711)
    provider = tomllib.loads(text)["model_providers"]["board"]
    assert provider == {
        "name": "OpenRouter",
        "base_url": "http://127.0.0.1:4711/v1",
        "env_key": CODEX_TOKEN,
    }
    assert "sk-" not in text


def test_the_codex_login_is_reached_only_through_the_broker() -> None:
    login = conn("l", "codex-login", "https://chatgpt.com/backend-api/codex")
    with pytest.raises(ConflictError) as caught:
        codex_config(login, "gpt", None, None)
    assert str(caught.value) == "a codex-login connection is reached only through the key broker"
    assert (
        tomllib.loads(codex_config(login, "gpt", None, 99)[0])["model_providers"]["board"][
            "base_url"
        ]
        == "http://127.0.0.1:99/v1"
    )


def test_the_untrusted_entry_is_keyed_by_the_path_whole() -> None:
    table = tomllib.loads(codex_untrusted('/w/a"b'))
    assert table["projects"]['/w/a"b']["trust_level"] == "untrusted"
    table = tomllib.loads(codex_untrusted("/w/a\\b\nc"))
    assert list(table["projects"]) == ["/w/a\\b\nc"]


def test_the_golden_chatgpt_login_gives_its_token_and_account_and_hides_the_token() -> None:
    login = codex_login((GOLDEN / "codex_login" / "auth.json").read_text(encoding="utf-8"))
    assert login.access_token.get_secret_value() == "fake-access-token"
    assert login.account_id == "fake-account"
    assert "fake-access-token" not in repr(login)
    assert "fake-access-token" not in str(login)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "[]",
        "{}",
        '{"auth_mode":"apikey","OPENAI_API_KEY":"sk-x"}',
        '{"auth_mode":"apikey","tokens":{"access_token":"a","account_id":"b"}}',
        '{"auth_mode":"chatgpt","tokens":{"access_token":"a"}}',
        '{"auth_mode":"chatgpt","tokens":{"access_token":"","account_id":"b"}}',
        '{"auth_mode":"chatgpt","tokens":{"account_id":"b"}}',
    ],
)
def test_a_file_that_is_not_a_chatgpt_login_is_refused(text: str) -> None:
    with pytest.raises(BadRequestError):
        codex_login(text)


def test_the_api_key_golden_says_it_is_not_a_chatgpt_login_and_names_no_key() -> None:
    text = (GOLDEN / "codex_login_api_key" / "auth.json").read_text(encoding="utf-8")
    with pytest.raises(BadRequestError) as caught:
        codex_login(text)
    assert str(caught.value) == "the codex login is not a ChatGPT login"
    assert "fake-key" not in str(caught.value)


def test_a_login_status_answers_for_a_chatgpt_login_and_words_the_rest() -> None:
    login = conn("l", "codex-login", "https://chatgpt.com/backend-api/codex")
    good = (GOLDEN / "codex_login" / "auth.json").read_text(encoding="utf-8")
    assert login_status(login, "/h/.codex/auth.json", good) == Status(name="l", answers=True)
    assert login_status(login, "/h/.codex/auth.json", None) == Status(
        name="l",
        answers=False,
        problem="no codex login at /h/.codex/auth.json: run `codex` once on this machine",
    )
    assert login_status(login, "f", "{}").problem == "the codex login is not a ChatGPT login"


def test_a_login_reach_is_answers_or_no_usable_login() -> None:
    assert login_reach(Status(name="l", answers=True)) == "answers"
    assert login_reach(Status(name="l", answers=False)) == "no usable codex login"
    assert login_reach(None) == "no usable codex login"


def test_a_connection_that_needs_the_broker_gets_no_direct_codex_config() -> None:
    router = conn("r", "openrouter", "https://openrouter.ai/api", "OPENROUTER_API_KEY")
    with pytest.raises(ConflictError) as caught:
        codex_config(router, "m", KEY, None)
    assert str(caught.value) == (
        "connection r holds a key, so a codex run reaches it only through the key broker"
    )
