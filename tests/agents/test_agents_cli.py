"""The commands: the table of agents, the exit code of a failed check, and the rules of
`secret set`'s options, with a key value that never reaches the output."""

import argparse
from pathlib import Path
from typing import override

import pytest

from agents_support import FakeStore, agents_fixture, clock_fixture, store_fixture  # noqa: F401
from code_factory.agents.cli import agents_command, connections_command, secret_command
from code_factory.agents.models.agents import AgentChange
from code_factory.agents.models.connections import ConnectionChange
from code_factory.agents.service import AgentService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.settings.service import SettingsService


@pytest.fixture
def services(agents: AgentService, uow: UnitOfWork) -> Services:
    registry = Services()
    registry.add(AgentService, agents)
    registry.add(SettingsService, SettingsService(uow))
    return registry


async def run(command: Command, services: Services, **fields: object) -> int:
    namespace = argparse.Namespace(**{"name": None, "repository": None, "url": None, **fields})
    assert command.run_async is not None
    return await command.run_async(namespace, services)


async def test_the_agents_table_lists_each_agent_with_its_columns_and_pause(
    agents: AgentService, services: Services, capsys: pytest.CaptureFixture[str]
) -> None:
    await agents.add_agent(AgentChange(name="writer", roles=["spec", "build"], model="m-1"))
    await agents.add_agent(AgentChange(name="rev", roles=["review"], paused=True))
    assert await run(agents_command, services, action="list") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == [
        "NAME",
        "RUNTIME",
        "CONNECTION",
        "MODEL",
        "COLUMNS",
        "PAUSED",
        "CHECK",
    ]
    assert lines[1].split() == ["writer", "claude", "-", "m-1", "spec,build", "no"]
    assert lines[2].split() == ["rev", "claude", "-", "-", "review", "yes"]


async def test_a_check_of_an_agent_that_cannot_be_checked_is_a_refusal_with_its_sentence(
    agents: AgentService, services: Services
) -> None:
    await agents.add_agent(AgentChange(name="plain", model="m"))
    with pytest.raises(BadRequestError):
        await run(agents_command, services, action="check", name="plain")
    with pytest.raises(BadRequestError):
        await run(agents_command, services, action="check")


async def test_the_connections_table_shows_a_key_as_set_or_not_never_its_value(
    agents: AgentService,
    services: Services,
    store: FakeStore,
    capsys: pytest.CaptureFixture[str],
) -> None:
    await agents.add_connection(
        ConnectionChange(name="cloud", kind="openrouter", key_env="OPENROUTER_API_KEY")
    )
    store.keys["OPENROUTER_API_KEY"] = "sk-hidden"
    assert await run(connections_command, services, action="list") == 0
    out = capsys.readouterr().out
    assert out.splitlines()[1].split() == [
        "cloud",
        "openrouter",
        "https://openrouter.ai/api",
        "set",
    ]
    assert "sk-hidden" not in out


async def test_secret_status_says_set_or_not_set_and_remove_forgets(
    services: Services, store: FakeStore, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await run(secret_command, services, action="status", name="K_API") == 0
    store.keys["K_API"] = "sk-hidden"
    assert await run(secret_command, services, action="status", name="K_API") == 0
    assert await run(secret_command, services, action="remove", name="K_API") == 0
    out = capsys.readouterr().out
    assert out.splitlines() == ["not set", "set", "removed"]
    assert "sk-hidden" not in out
    assert store.keys == {}


async def test_a_key_name_that_could_be_an_option_is_refused(services: Services) -> None:
    with pytest.raises(BadRequestError) as caught:
        await run(secret_command, services, action="status", name="-x")
    assert str(caught.value) == "a key name is capitals, digits and _"


async def test_options_belong_to_an_intake_key_only(services: Services) -> None:
    with pytest.raises(BadRequestError) as caught:
        await run(
            secret_command,
            services,
            action="set",
            name="K_API",
            repository="/r",
            url="https://api.linear.app/graphql",
        )
    assert str(caught.value) == (
        "only an intake key (CODE_FACTORY_INTAKE_...) is stored with --repository and --url"
    )
    with pytest.raises(BadRequestError) as missing:
        await run(secret_command, services, action="set", name="CODE_FACTORY_INTAKE_LINEAR")
    assert str(missing.value) == (
        "CODE_FACTORY_INTAKE_LINEAR is an intake key: name the repository it serves with "
        "--repository and its tracker's address with --url"
    )


class FailingStore(FakeStore):
    @override
    async def store(self, name: str) -> int:
        return 7


async def test_an_intake_key_is_granted_before_it_is_stored_and_the_grant_goes_when_storing_fails(
    agents: AgentService, services: Services, store: FakeStore
) -> None:
    settings = services.get(SettingsService)
    name = "CODE_FACTORY_INTAKE_LINEAR"
    code = await run(
        secret_command,
        services,
        action="set",
        name=name,
        repository="/r",
        url="https://api.linear.app/graphql",
    )
    assert code == 0
    assert store.keys[name] == "stored"
    grant = await settings.intake_grant(name)
    assert grant is not None
    assert grant.url == "https://api.linear.app/graphql"

    agents._store = FailingStore()
    other = "CODE_FACTORY_INTAKE_JIRA"
    code = await run(
        secret_command,
        services,
        action="set",
        name=other,
        repository="/r",
        url="https://api.linear.app/graphql",
    )
    assert code == 7
    assert await settings.intake_grant(other) is None


async def test_a_plain_key_is_stored_without_a_grant(
    services: Services, store: FakeStore, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await run(secret_command, services, action="set", name="ANTHROPIC_API_KEY") == 0
    assert store.keys["ANTHROPIC_API_KEY"] == "stored"
    assert capsys.readouterr().out == "ANTHROPIC_API_KEY stored\n"


async def test_a_failed_rotation_keeps_the_grant_the_old_key_was_stored_under(
    agents: AgentService, services: Services
) -> None:
    settings = services.get(SettingsService)
    name = "CODE_FACTORY_INTAKE_LINEAR"
    url = "https://api.linear.app/graphql"
    await settings.grant_intake_key(name, Path("/old"), url)
    agents._store = FailingStore()
    code = await run(secret_command, services, action="set", name=name, repository="/new", url=url)
    assert code == 7
    kept = await settings.intake_grant(name)
    assert kept is not None
    assert kept.repository == "/old"
