"""Tracker key grants: which repository and address a key may serve, against the test database."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError
from code_factory.settings.models.problems import IntakeGrant
from code_factory.settings.service import SettingsService

JIRA = "CODE_FACTORY_INTAKE_JIRA"
LINEAR = "CODE_FACTORY_INTAKE_LINEAR"


@pytest.fixture
def service(uow: UnitOfWork) -> SettingsService:
    return SettingsService(uow)


async def test_a_grant_is_stored_and_read_back(service: SettingsService) -> None:
    granted = await service.grant_intake_key(JIRA, Path("/work/repo"), "https://acme.atlassian.net")
    assert granted == IntakeGrant(
        key_name=JIRA, repository="/work/repo", url="https://acme.atlassian.net"
    )
    assert await service.intake_grant(JIRA) == granted


async def test_a_trailing_slash_is_not_stored(service: SettingsService) -> None:
    granted = await service.grant_intake_key(JIRA, Path("/r"), "https://acme.atlassian.net/")
    assert granted.url == "https://acme.atlassian.net"


async def test_a_second_grant_of_the_name_replaces_the_first(service: SettingsService) -> None:
    await service.grant_intake_key(JIRA, Path("/one"), "https://one.atlassian.net")
    await service.grant_intake_key(JIRA, Path("/two"), "https://two.atlassian.net")
    assert await service.list_intake_grants() == [
        IntakeGrant(key_name=JIRA, repository="/two", url="https://two.atlassian.net")
    ]


async def test_a_name_outside_the_intake_prefix_is_refused(service: SettingsService) -> None:
    for name in ("ANTHROPIC_API_KEY", "CODE_FACTORY_INTAKE_", "CODE_FACTORY_INTAKE_jira"):
        with pytest.raises(BadRequestError, match="is not an intake key name"):
            await service.grant_intake_key(name, Path("/r"), "https://acme.atlassian.net")
    assert await service.list_intake_grants() == []


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example.com",
        "https://api.linear.app.evil.com/graphql",
        "https://user@acme.atlassian.net",
        "https://api.linear.app:pw@evil.com",
        "https://acme.atlassian.net/#frag",
        "ftp://acme.atlassian.net",
        "acme.atlassian.net",
        "",
    ],
)
async def test_an_address_a_key_may_not_go_to_is_refused(
    service: SettingsService, url: str
) -> None:
    with pytest.raises(BadRequestError, match="is not an address a tracker key may go to"):
        await service.grant_intake_key(JIRA, Path("/r"), url)
    assert await service.intake_grant(JIRA) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://api.linear.app/graphql",
        "https://acme.atlassian.net",
        "https://slack.com/api",
        "http://localhost:4100",
        "http://127.0.0.1:4100/graphql",
    ],
)
async def test_the_trackers_own_addresses_and_this_machine_are_accepted(
    service: SettingsService, url: str
) -> None:
    granted = await service.grant_intake_key(LINEAR, Path("/r"), url)
    assert granted.url == url


async def test_revoke_deletes_and_says_whether_there_was_a_grant(service: SettingsService) -> None:
    await service.grant_intake_key(JIRA, Path("/r"), "https://acme.atlassian.net")
    assert await service.revoke_intake_key(JIRA) is True
    assert await service.revoke_intake_key(JIRA) is False
    assert await service.intake_grant(JIRA) is None


async def test_grants_are_listed_by_name(service: SettingsService) -> None:
    await service.grant_intake_key(LINEAR, Path("/r"), "https://api.linear.app/graphql")
    await service.grant_intake_key(JIRA, Path("/r"), "https://acme.atlassian.net")
    assert [g.key_name for g in await service.list_intake_grants()] == [JIRA, LINEAR]


async def test_the_database_refuses_a_name_outside_the_prefix(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_intake_key_grants_key_name"):
        await db_session.execute(
            text("INSERT INTO intake_key_grants (key_name, repository, url) VALUES (:n, '/r', :u)"),
            {"n": "OTHER_KEY", "u": "https://acme.atlassian.net"},
        )


async def test_the_database_refuses_an_address_that_is_no_http_url(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(IntegrityError, match="ck_intake_key_grants_url"):
        await db_session.execute(
            text("INSERT INTO intake_key_grants (key_name, repository, url) VALUES (:n, '/r', :u)"),
            {"n": JIRA, "u": "ftp://acme.atlassian.net"},
        )
