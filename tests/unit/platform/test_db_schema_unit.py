"""`CODE_FACTORY_DB_SCHEMA`: one database holds isolated copies of the application tables."""

import pytest

from code_factory.platform.config import DATABASE_URL_VARIABLE, load_settings
from code_factory.platform.errors import SettingsError


@pytest.mark.parametrize("name", ["", "1x", "a-b", 'a"b', "a" * 64, "Mixed Case"])
def test_a_schema_name_that_is_not_a_plain_identifier_is_refused(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODE_FACTORY_DB_SCHEMA", name)
    monkeypatch.setenv(DATABASE_URL_VARIABLE, "postgresql+asyncpg://u:p@127.0.0.1:5432/x_test")
    with pytest.raises(SettingsError, match="CODE_FACTORY_DB_SCHEMA is invalid"):
        load_settings()
