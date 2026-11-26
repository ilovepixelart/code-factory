"""A tracker key is used only for the repository and address this machine granted it to."""

from pathlib import Path
from typing import cast

import pytest
from pydantic import SecretStr

from code_factory.agents.service import AgentService
from code_factory.delivery.service.neighbours import PlacesAdapter
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.settings.models.config import RepositoryConfig
from code_factory.settings.models.problems import IntakeGrant
from code_factory.settings.service import SettingsService

KEY = "CODE_FACTORY_INTAKE_LINEAR"
LINEAR = "https://api.linear.app/graphql"
ROOT = Path("/work/shop")


class _Repositories:
    async def get(self, name: str) -> Path:  # noqa: ARG002
        return ROOT


class _Settings:
    def __init__(self, grant: IntakeGrant | None) -> None:
        self.grant = grant

    async def load(self, root: Path) -> RepositoryConfig:  # noqa: ARG002
        intake = {"linear_token_env": KEY, "linear_label": "board"}
        return RepositoryConfig.model_validate({"intake": intake})

    async def intake_grant(self, name: str) -> IntakeGrant | None:
        return self.grant if self.grant is not None and name == self.grant.key_name else None


class _Keys:
    def __init__(self, value: str | None) -> None:
        self.value = value

    async def read_key(self, name: str) -> SecretStr | None:  # noqa: ARG002
        return None if self.value is None else SecretStr(self.value)


def _places(grant: IntakeGrant | None, key: str | None = "lin_api_x") -> PlacesAdapter:
    services = Services()
    services.add(RepositoryService, cast("RepositoryService", _Repositories()))
    services.add(SettingsService, cast("SettingsService", _Settings(grant)))
    services.add(AgentService, cast("AgentService", _Keys(key)))
    return PlacesAdapter(services)


async def test_a_key_granted_to_this_repository_and_address_reads_linear() -> None:
    grant = IntakeGrant(key_name=KEY, repository=str(ROOT), url=LINEAR + "/")

    trackers = (await _places(grant).switches("shop")).trackers

    assert [(t.kind, t.url, t.label, t.key.get_secret_value()) for t in trackers] == [
        ("linear", LINEAR, "board", "lin_api_x")
    ]


@pytest.mark.parametrize(
    ("grant", "key"),
    [
        (IntakeGrant(key_name=KEY, repository="/work/other", url=LINEAR), "lin_api_x"),
        (IntakeGrant(key_name=KEY, repository=str(ROOT), url="https://evil.test/graphql"), "x"),
        (None, "lin_api_x"),
        (IntakeGrant(key_name=KEY, repository=str(ROOT), url=LINEAR), None),
    ],
    ids=["another-repository", "another-address", "no-grant", "no-key"],
)
async def test_a_key_not_granted_here_or_not_stored_reads_nothing(
    grant: IntakeGrant | None, key: str | None
) -> None:
    assert (await _places(grant, key).switches("shop")).trackers == ()
