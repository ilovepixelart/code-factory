"""`code-factory sample-*`: a schema of its own, loaded with a named sample."""

import asyncio
import hashlib
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import text

from code_factory.platform.config import DATABASE_URL_VARIABLE, Settings
from code_factory.platform.db import create_engine

COMMAND = str(Path(sys.executable).parent / "code-factory")
# What the browser tests send as the owner's cookie: `cfs_` and the url-safe base64 of 32 bytes
# of 0x2a (hand-worked: 0x2a is `*`, three of them encode as `Kioq`).
OWNER_TOKEN = "cfs_" + "Kioq" * 10 + "Kio"

# Each test starts the command line two or three times (a new interpreter, a migration from
# base); alone that takes 8 to 11 s at a load average of 25 to 30, so the suite default of 30 s
# is too close when every agent runs its gate at once.
pytestmark = pytest.mark.timeout(120)


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # our own console script, no shell
        [COMMAND, *args], env=env, capture_output=True, text=True, check=False, timeout=60
    )


@pytest.fixture
async def sample_env(settings: Settings, migrated: None) -> AsyncGenerator[dict[str, str]]:  # noqa: ARG001
    schema = f"sample_{uuid.uuid4().hex[:10]}"
    env = {**os.environ, "CODE_FACTORY_DB_SCHEMA": schema}
    yield env
    await asyncio.to_thread(_run, env, "sample-drop")


async def _digests(settings: Settings, schema: str) -> list[str]:
    engine = create_engine(settings.model_copy(update={"db_schema": schema}))
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(text("SELECT digest FROM auth_tokens"))
            return [row[0] for row in rows]
    finally:
        await engine.dispose()


async def test_prepare_and_load_leave_a_migrated_schema_holding_the_owners_fixed_session(
    settings: Settings, sample_env: dict[str, str]
) -> None:
    prepared = await asyncio.to_thread(_run, sample_env, "sample-prepare")
    loaded = await asyncio.to_thread(_run, sample_env, "sample-load", "empty")

    assert (prepared.returncode, loaded.returncode) == (0, 0), (prepared.stderr, loaded.stderr)
    digests = await _digests(settings, sample_env["CODE_FACTORY_DB_SCHEMA"])
    assert hashlib.sha256(OWNER_TOKEN.encode()).hexdigest() in digests


async def test_loading_into_a_schema_that_already_holds_a_sample_is_refused(
    settings: Settings, sample_env: dict[str, str]
) -> None:
    await asyncio.to_thread(_run, sample_env, "sample-prepare")
    await asyncio.to_thread(_run, sample_env, "sample-load", "empty")
    again = await asyncio.to_thread(_run, sample_env, "sample-load", "empty")

    assert again.returncode == 1
    assert "the schema already holds a sample; run sample-drop, then sample-prepare" in again.stderr
    # The session and the spent link it was bought with.
    assert len(await _digests(settings, sample_env["CODE_FACTORY_DB_SCHEMA"])) == 2


async def test_an_unknown_sample_is_refused_naming_the_known_ones(
    sample_env: dict[str, str],
) -> None:
    await asyncio.to_thread(_run, sample_env, "sample-prepare")
    refused = await asyncio.to_thread(_run, sample_env, "sample-load", "nonesuch")
    assert refused.returncode == 1
    assert "unknown sample nonesuch; the samples are: empty" in refused.stderr


async def test_drop_removes_the_schema(settings: Settings, sample_env: dict[str, str]) -> None:
    await asyncio.to_thread(_run, sample_env, "sample-prepare")
    dropped = await asyncio.to_thread(_run, sample_env, "sample-drop")
    assert dropped.returncode == 0
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            found = await connection.execute(
                text("SELECT 1 FROM pg_namespace WHERE nspname = :n"),
                {"n": sample_env["CODE_FACTORY_DB_SCHEMA"]},
            )
            assert found.first() is None
    finally:
        await engine.dispose()


REFUSED_TARGET = (
    "the sample commands change a database wholesale and run only against a _test database on "
    "this machine"
)


@pytest.mark.parametrize("command", [["sample-prepare"], ["sample-drop"], ["sample-load", "empty"]])
@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://nobody:pw@127.0.0.1:1/code_factory",
        "postgresql+asyncpg://nobody:pw@127.0.0.1:1/code_factory_test?database=code_factory",
        "postgresql+asyncpg://nobody:pw@db.example.com:1/code_factory_test",
    ],
)
def test_a_target_that_is_not_a_test_database_here_is_refused_before_any_connection(
    command: list[str], url: str
) -> None:
    env = {**os.environ, DATABASE_URL_VARIABLE: url, "CODE_FACTORY_DB_SCHEMA": "sample_x"}
    refused = _run(env, *command)
    assert refused.returncode == 1
    assert REFUSED_TARGET in refused.stderr
    assert "pw" not in refused.stderr


@pytest.mark.parametrize("command", [["sample-prepare"], ["sample-drop"], ["sample-load", "empty"]])
def test_the_default_schema_is_never_prepared_dropped_or_loaded(command: list[str]) -> None:
    env = {k: v for k, v in os.environ.items() if k != "CODE_FACTORY_DB_SCHEMA"}
    refused = _run(env, *command)
    assert refused.returncode == 1
    assert "set CODE_FACTORY_DB_SCHEMA to a schema of its own" in refused.stderr
