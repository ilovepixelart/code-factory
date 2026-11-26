"""The startup check: the app never migrates, it reads the state and refuses what it cannot read."""

import pytest

from app_lifespan import running_lifespan
from code_factory.app import create_app
from code_factory.platform.config import Settings
from code_factory.platform.db import (
    DATA_FORMAT_VERSION,
    EXPECTED_REVISION,
    SchemaState,
    verify_schema,
)
from code_factory.platform.errors import (
    DatabaseUnavailableError,
    SchemaMismatchError,
)

UPGRADE = "run `code-factory db upgrade`"


def test_a_state_this_build_expects_is_accepted() -> None:
    verify_schema(SchemaState(revision=EXPECTED_REVISION, data_format=DATA_FORMAT_VERSION))


@pytest.mark.parametrize(
    ("state", "sentence"),
    [
        (SchemaState(None, None), f"the database has no schema yet; {UPGRADE}"),
        (
            SchemaState("abc123", 1),
            (
                f"the database is at revision abc123 but this build expects {EXPECTED_REVISION}; "
                f"{UPGRADE}, or install the build that wrote the database if it is newer"
            ),
        ),
        (
            SchemaState(EXPECTED_REVISION, None),
            f"schema_info holds no data format version; {UPGRADE}",
        ),
        (
            SchemaState(EXPECTED_REVISION, DATA_FORMAT_VERSION + 1),
            (
                f"the database data format is {DATA_FORMAT_VERSION + 1} but this build reads "
                f"{DATA_FORMAT_VERSION}; install a newer code-factory"
            ),
        ),
        (
            SchemaState(EXPECTED_REVISION, DATA_FORMAT_VERSION - 1),
            (
                f"the database data format is {DATA_FORMAT_VERSION - 1} but this build reads "
                f"{DATA_FORMAT_VERSION}; {UPGRADE}"
            ),
        ),
    ],
)
def test_a_state_it_cannot_read_is_refused_with_the_repair(
    state: SchemaState, sentence: str
) -> None:
    with pytest.raises(SchemaMismatchError) as raised:
        verify_schema(state)
    assert str(raised.value) == sentence


async def test_an_unreachable_database_stops_the_app_with_one_sentence_and_no_password(
    offline_settings: Settings,
) -> None:
    lifespan = running_lifespan(create_app(offline_settings, guarded=False))
    with pytest.raises(DatabaseUnavailableError) as raised:
        async with lifespan:
            pytest.fail("the app started without a database")
    message = str(raised.value)
    assert message.startswith("the database at 127.0.0.1:1/never_connected is not reachable (")
    assert "not-a-password" not in message
    assert "\n" not in message
