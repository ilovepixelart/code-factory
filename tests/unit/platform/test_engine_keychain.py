"""A database URL without a password takes it from the keychain; one with a password keeps it."""

import pytest
from pydantic import SecretStr

from code_factory.platform.config import Settings
from code_factory.platform.db import create_engine
from code_factory.platform.errors import SettingsError


def _settings(url: str) -> Settings:
    return Settings(database_url=SecretStr(url), _env_file=None)


async def test_a_url_without_a_password_is_given_the_keychains() -> None:
    asked: list[str] = []

    def keychain(account: str) -> str:
        asked.append(account)
        return "from-keychain"

    engine = create_engine(_settings("postgresql+asyncpg://board@127.0.0.1:5432/x_test"), keychain)

    assert (engine.url.password, asked) == ("from-keychain", ["board"])
    await engine.dispose()


async def test_a_url_with_a_password_never_asks_the_keychain() -> None:
    def keychain(_account: str) -> str:
        raise AssertionError

    engine = create_engine(_settings("postgresql+asyncpg://board:given@127.0.0.1/x_test"), keychain)

    assert engine.url.password == "given"  # noqa: S105  # the test URL's own
    await engine.dispose()


def test_no_password_anywhere_says_how_to_add_one_and_never_the_url() -> None:
    given = _settings("postgresql+asyncpg://board@127.0.0.1/x_test")
    with pytest.raises(SettingsError) as refused:
        create_engine(given, lambda _a: None)
    assert str(refused.value) == (
        "CODE_FACTORY_DATABASE_URL names no password and the keychain holds none for board: add "
        "it with security add-generic-password -a board -s code-factory-postgres -w"
    )
