"""What the key broker reads of the agents module: a connection by name, its checked address,
and the codex login read fresh."""

import json
from pathlib import Path

import pytest

from agents_support import FakeStore, agents_fixture, clock_fixture, store_fixture  # noqa: F401
from code_factory.agents.models.connections import ConnectionChange, ConnectionDefinition
from code_factory.agents.service import AgentService
from code_factory.platform.errors import BadRequestError, NotFoundError, UnavailableError

GOLDEN = Path(__file__).parents[2] / "support/golden" / "agents"


def conn(**fields: object) -> ConnectionChange:
    return ConnectionChange.model_validate(fields)


async def test_a_connection_is_read_by_name(agents: AgentService) -> None:
    await agents.add_connection(
        conn(
            name="cloud",
            kind="openrouter",
            key_env="OPENROUTER_API_KEY",
            management_key_env="OPENROUTER_MANAGEMENT_API_KEY",
        )
    )
    found = await agents.connection_definition("cloud")
    assert found.base_url == "https://openrouter.ai/api"
    assert found.key_env == "OPENROUTER_API_KEY"
    assert found.management_key_env == "OPENROUTER_MANAGEMENT_API_KEY"


async def test_an_unknown_connection_is_not_found(agents: AgentService) -> None:
    with pytest.raises(NotFoundError, match="no such connection"):
        await agents.connection_definition("nope")


def test_a_connection_that_keeps_the_rules_is_checked_clean_and_one_that_breaks_them_is_not(
    agents: AgentService,
) -> None:
    ok = ConnectionDefinition(
        name="c",
        kind="anthropic",
        base_url="https://api.anthropic.com",
        key_env="ANTHROPIC_API_KEY",
    )
    agents.check_connection(ok)
    bad = ok.model_copy(update={"key_env": "GITHUB_TOKEN"})
    with pytest.raises(BadRequestError):
        agents.check_connection(bad)


@pytest.mark.parametrize(
    ("kind", "base_url", "key", "host"),
    [
        ("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY", "api.anthropic.com:443"),
        ("openrouter", "https://openrouter.ai/api", "OPENROUTER_API_KEY", "openrouter.ai:443"),
        ("ollama", "http://localhost:11434", "", "localhost:11434"),
        ("custom", "http://127.0.0.1:8123", "", "127.0.0.1:8123"),
        ("lm-studio", "http://localhost", "", "localhost:80"),
    ],
)
def test_the_model_host_is_the_checked_hosts_and_port(
    agents: AgentService, kind: str, base_url: str, key: str, host: str
) -> None:
    connection = ConnectionDefinition(name="c", kind=kind, base_url=base_url, key_env=key)
    assert agents.model_host(connection) == host


async def test_the_codex_login_is_read_on_every_call(agents: AgentService, tmp_path: Path) -> None:
    folder = tmp_path / "codex"
    folder.mkdir()
    (folder / "auth.json").write_text(
        (GOLDEN / "codex_login" / "auth.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    first = await agents.read_codex_login()
    assert first.account_id == "fake-account"
    changed = json.loads((folder / "auth.json").read_text(encoding="utf-8"))
    changed["tokens"]["account_id"] = "second-account"
    (folder / "auth.json").write_text(json.dumps(changed), encoding="utf-8")
    assert (await agents.read_codex_login()).account_id == "second-account"


@pytest.mark.parametrize("which", ["missing", "api_key", "garbage"])
async def test_an_unusable_codex_login_is_unavailable_with_the_sentence(
    agents: AgentService, tmp_path: Path, which: str
) -> None:
    folder = tmp_path / "codex"
    folder.mkdir()
    if which == "api_key":
        (folder / "auth.json").write_text(
            (GOLDEN / "codex_login_api_key" / "auth.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    elif which == "garbage":
        (folder / "auth.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(UnavailableError) as error:
        await agents.read_codex_login()
    assert "codex" in str(error.value)
    assert "fake-key" not in str(error.value)
