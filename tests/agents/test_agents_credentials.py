"""The credential store adapter against a fake `security` / `secret-tool` program: the arguments
it passes, what it does with the output, and that a key is never in a log or an error."""

import logging
import os
import stat
import sys
from pathlib import Path

import pytest

from code_factory.agents.adapters.credentials import CredentialStore
from code_factory.platform.errors import BadRequestError

MACOS = sys.platform == "darwin"


def fake_program(folder: Path, body: str) -> Path:
    """An executable shell script; `$LOG` names the file it records its arguments in."""
    program = folder / "store"
    program.write_text(f'#!/bin/sh\necho "$@" >> "$LOG"\n{body}\n', encoding="utf-8")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    return program


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "calls.log"
    monkeypatch.setenv("LOG", str(path))
    return path


def lines_of(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def lookup_arguments(name: str) -> str:
    if MACOS:
        return f"find-generic-password -s code-factory -a {name} -w"
    return f"lookup service code-factory account {name}"


async def test_a_key_is_looked_up_by_service_and_name_and_loses_its_trailing_newline(
    tmp_path: Path, log: Path
) -> None:
    store = CredentialStore(program=fake_program(tmp_path, "printf 'sk-1\\n'"))
    key = await store.read("ANTHROPIC_API_KEY")
    assert key is not None
    assert key.get_secret_value() == "sk-1"
    assert lines_of(log) == [lookup_arguments("ANTHROPIC_API_KEY")]


async def test_an_empty_value_or_a_failing_store_is_no_key(tmp_path: Path, log: Path) -> None:
    assert (
        await CredentialStore(program=fake_program(tmp_path, "printf '\\n'")).read("K_API") is None
    )
    assert await CredentialStore(program=fake_program(tmp_path, "exit 44")).read("K_API") is None
    assert lines_of(log)


@pytest.mark.usefixtures("log")
async def test_the_environment_answers_when_the_store_has_nothing_and_loses_to_the_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("K_API", "from-env")
    (tmp_path / "empty").mkdir()
    (tmp_path / "full").mkdir()
    empty = CredentialStore(program=fake_program(tmp_path / "empty", "exit 44"))
    found = await empty.read("K_API")
    assert found is not None
    assert found.get_secret_value() == "from-env"
    full = CredentialStore(program=fake_program(tmp_path / "full", "printf 'from-store'"))
    stored = await full.read("K_API")
    assert stored is not None
    assert stored.get_secret_value() == "from-store"
    monkeypatch.setenv("K_API", "")
    assert await empty.read("K_API") is None


async def test_a_missing_program_is_no_key_not_an_error(tmp_path: Path) -> None:
    store = CredentialStore(program=tmp_path / "absent")
    assert await store.read("K_API") is None
    assert await store.has("K_API") is False


@pytest.mark.parametrize("name", ["-x", "--help", "lower", "a b", "", "A.B", "A\nB"])
async def test_a_name_that_could_be_an_option_is_refused_before_any_process(
    tmp_path: Path, log: Path, name: str
) -> None:
    store = CredentialStore(program=fake_program(tmp_path, "printf 'v'"))
    with pytest.raises(BadRequestError) as caught:
        await store.read(name)
    assert str(caught.value) == "a key name is capitals, digits and _"
    assert not log.exists()  # noqa: ASYNC240  # a stat, after the call returned


@pytest.mark.usefixtures("log")
async def test_a_hung_program_is_killed_and_reaped(tmp_path: Path) -> None:
    pids = tmp_path / "pid"
    store = CredentialStore(
        # Give the fixture process time to publish its PID on a busy CI runner.
        program=fake_program(tmp_path, f"echo $$ > {pids}\nsleep 30"),
        timeout_s=2.0,
    )
    assert await store.read("K_API") is None
    pid = int(lines_of(pids)[0])
    assert pid > 1
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.usefixtures("log")
async def test_a_value_is_in_no_log_record_and_no_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    store = CredentialStore(program=fake_program(tmp_path, "echo sekret >&2\nprintf 'sekret'"))
    key = await store.read("K_API")
    assert key is not None
    assert "sekret" not in repr(key)
    assert "sekret" not in caplog.text
    failing = CredentialStore(program=fake_program(tmp_path, "echo sekret >&2\nexit 1"))
    assert await failing.read("K_API") is None
    assert "sekret" not in caplog.text


async def test_has_and_remove_use_the_stores_own_commands(tmp_path: Path, log: Path) -> None:
    store = CredentialStore(program=fake_program(tmp_path, "printf 'v'"))
    assert await store.has("K_API") is True
    assert await store.remove("K_API") is True
    calls = lines_of(log)
    removal = (
        "delete-generic-password -s code-factory -a K_API"
        if MACOS
        else "clear service code-factory account K_API"
    )
    assert calls == [lookup_arguments("K_API"), removal]


async def test_storing_a_key_passes_no_value_and_gives_the_exit_code(
    tmp_path: Path, log: Path
) -> None:
    store = CredentialStore(program=fake_program(tmp_path, "exit 3"))
    assert await store.store("K_API") == 3
    expected = (
        "add-generic-password -U -s code-factory -a K_API -w"
        if MACOS
        else "store --label code-factory K_API service code-factory account K_API"
    )
    assert lines_of(log) == [expected]


@pytest.mark.usefixtures("log")
async def test_a_store_prompt_that_outlives_its_limit_is_terminated_and_reaped(
    tmp_path: Path,
) -> None:
    pids = tmp_path / "pid"
    store = CredentialStore(
        program=fake_program(tmp_path, f"echo $$ > {pids}\nsleep 30"),
        store_timeout_s=2.0,
    )
    assert await store.store("K_API") == 1
    pid = int(lines_of(pids)[0])
    assert pid > 1
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
