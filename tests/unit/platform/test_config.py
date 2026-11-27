import os
import tempfile
from pathlib import Path

import pytest

from code_factory.platform import config as config_module
from code_factory.platform.config import (
    DATABASE_URL_VARIABLE,
    ENV_NAME_VARIABLE,
    Settings,
    _env_files,
    load_settings,
)
from code_factory.platform.db import unavailable
from code_factory.platform.errors import SettingsError

LEAK_MARKER = "s3cr3t-pw"
URL = f"postgresql+asyncpg://code_factory:{LEAK_MARKER}@127.0.0.1:5432/code_factory_test"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir("/")  # no env file is found
    monkeypatch.delenv(DATABASE_URL_VARIABLE, raising=False)
    monkeypatch.delenv(ENV_NAME_VARIABLE, raising=False)


def test_missing_database_url_names_the_variable_and_the_keychain_command() -> None:
    with pytest.raises(SettingsError) as raised:
        load_settings()
    message = str(raised.value)
    assert "CODE_FACTORY_DATABASE_URL is not set" in message
    assert "security find-generic-password -a code_factory -s code-factory-postgres -w" in message


def test_a_url_with_the_wrong_scheme_is_refused_without_echoing_the_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, f"postgresql://code_factory:{LEAK_MARKER}@h:5432/x")
    with pytest.raises(SettingsError) as raised:
        load_settings()
    assert "the scheme must be postgresql+asyncpg" in str(raised.value)
    assert LEAK_MARKER not in str(raised.value)


def test_the_password_is_in_neither_repr_nor_str_nor_the_printable_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    settings = load_settings()
    assert LEAK_MARKER not in repr(settings)
    assert LEAK_MARKER not in str(settings)
    assert LEAK_MARKER not in settings.model_dump_json()
    assert settings.database_target == "127.0.0.1:5432/code_factory_test"
    assert settings.database_url.get_secret_value() == URL


def test_defaults_and_the_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    monkeypatch.setenv("CODE_FACTORY_PORT", "4999")
    monkeypatch.setenv("CODE_FACTORY_LOG_LEVEL", "debug")
    settings = load_settings()
    assert (settings.host, settings.port, settings.log_level) == ("127.0.0.1", 4999, "DEBUG")


def test_an_out_of_range_port_is_one_sentence_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    monkeypatch.setenv("CODE_FACTORY_PORT", "70000")
    with pytest.raises(SettingsError, match="CODE_FACTORY_PORT is invalid"):
        load_settings()


def test_a_wildcard_bind_advertises_the_local_compose_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    monkeypatch.setenv("CODE_FACTORY_HOST", "0.0.0.0")  # noqa: S104  # bind setting only
    monkeypatch.setenv("CODE_FACTORY_PORT", "4010")

    assert load_settings().base_url == "http://127.0.0.1:4010"


@pytest.mark.parametrize("password", ["pa/ss", "pa?ss", "pa#ss", "pa%2Fss", "a/b?c#d:e"])
def test_a_password_with_url_characters_never_reaches_a_printable_form(
    monkeypatch: pytest.MonkeyPatch, password: str
) -> None:
    secret = password.replace("%2F", "/")
    monkeypatch.setenv(
        DATABASE_URL_VARIABLE,
        f"postgresql+asyncpg://code_factory:{password}@127.0.0.1:5432/code_factory_test",
    )
    settings = load_settings()
    assert settings.database_target == "127.0.0.1:5432/code_factory_test"
    unreachable = unavailable(settings, OSError("refused"))
    for printed in (settings.database_target, str(unreachable), repr(settings), str(settings)):
        assert secret not in printed
        assert password not in printed


def test_a_database_url_without_a_port_prints_its_host_and_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, "postgresql+asyncpg://u:pw@db.internal/code_factory")
    assert load_settings().database_target == "db.internal/code_factory"


@pytest.mark.parametrize(
    "authority_and_path",
    [
        "u:pa@ss@127.0.0.1:5432/x",
        "u:pa@ss/word@127.0.0.1:5432/x",
        "u:pa@ss:1@127.0.0.1:5432/x",
        "u:pa@127.0.0.1:5432/x@ss",
        "u:pa@127.0.0.1:5432/x?y=ss@z",
    ],
)
def test_an_unencoded_at_sign_in_the_password_is_refused_without_echoing_any_of_it(
    monkeypatch: pytest.MonkeyPatch, authority_and_path: str
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, f"postgresql+asyncpg://{authority_and_path}")
    with pytest.raises(SettingsError) as raised:
        load_settings()
    message = str(raised.value)
    assert "percent-encode" in message
    for fragment in ("pa", "ss", "word", "u:"):
        assert f"{fragment}@" not in message
        assert f"@{fragment}" not in message


@pytest.mark.parametrize("port", ["abc", "54x2", "-1x"])
def test_a_non_numeric_port_is_one_fixed_sentence(
    monkeypatch: pytest.MonkeyPatch, port: str
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, f"postgresql+asyncpg://u:{LEAK_MARKER}@h:{port}/x")
    with pytest.raises(SettingsError) as raised:
        load_settings()
    assert "cannot be parsed" in str(raised.value)
    assert LEAK_MARKER not in str(raised.value)


@pytest.mark.parametrize("failure", [ValueError, TypeError])
def test_whatever_the_parser_raises_is_replaced_by_a_fixed_sentence(
    monkeypatch: pytest.MonkeyPatch, failure: type[Exception]
) -> None:
    def parse(raw: str) -> object:
        raise failure(f"cannot parse {raw}")

    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    settings = load_settings()
    monkeypatch.setattr(config_module, "make_url", parse)
    with pytest.raises(SettingsError) as raised:
        _ = settings.database_target
    assert str(raised.value) == "the database URL cannot be parsed"
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__
    with pytest.raises(SettingsError) as at_load:
        load_settings()
    assert LEAK_MARKER not in str(at_load.value)
    assert "cannot be parsed" in str(at_load.value)


def _read_env_files(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    """Turn the env files on (conftest turns them off) as the working directory `directory`."""
    monkeypatch.chdir(directory)
    monkeypatch.setattr(
        Settings, "model_config", {**Settings.model_config, "env_file": _env_files()}
    )


def test_the_env_files_are_dot_env_then_dot_env_local_by_default() -> None:
    assert _env_files() == (".env", ".env.local")


def test_code_factory_env_adds_its_layer_between_the_two(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_NAME_VARIABLE, "dev-1_b")
    assert _env_files() == (".env", ".env.dev-1_b", ".env.local")


@pytest.mark.parametrize("name", ["../x", "a/b", "a.b", "a b", ".local", "x\n"])
def test_an_env_name_that_could_point_at_another_path_is_refused(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(ENV_NAME_VARIABLE, name)
    with pytest.raises(SettingsError, match=f"{ENV_NAME_VARIABLE} must hold only letters"):
        _env_files()


def test_each_layer_is_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(f"CODE_FACTORY_DATABASE_URL={URL}\n")
    (tmp_path / ".env.dev").write_text("CODE_FACTORY_PORT=4101\n")
    (tmp_path / ".env.local").write_text("CODE_FACTORY_HOST=0.0.0.0\n")
    monkeypatch.setenv(ENV_NAME_VARIABLE, "dev")
    _read_env_files(monkeypatch, tmp_path)
    settings = load_settings()
    assert settings.database_url.get_secret_value() == URL
    assert (settings.port, settings.host) == (4101, "0.0.0.0")  # noqa: S104


def test_the_later_layer_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(f"CODE_FACTORY_DATABASE_URL={URL}\nCODE_FACTORY_PORT=4101\n")
    (tmp_path / ".env.dev").write_text("CODE_FACTORY_PORT=4102\nCODE_FACTORY_LOG_LEVEL=debug\n")
    (tmp_path / ".env.local").write_text("CODE_FACTORY_PORT=4103\n")
    monkeypatch.setenv(ENV_NAME_VARIABLE, "dev")
    _read_env_files(monkeypatch, tmp_path)
    settings = load_settings()
    assert (settings.port, settings.log_level) == (4103, "DEBUG")


def test_the_named_layer_beats_dot_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(f"CODE_FACTORY_DATABASE_URL={URL}\nCODE_FACTORY_PORT=4101\n")
    (tmp_path / ".env.dev").write_text("CODE_FACTORY_PORT=4102\n")
    (tmp_path / ".env.prod").write_text("CODE_FACTORY_PORT=4199\n")
    monkeypatch.setenv(ENV_NAME_VARIABLE, "dev")
    _read_env_files(monkeypatch, tmp_path)
    assert load_settings().port == 4102


def test_the_process_environment_beats_every_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env.local").write_text(
        f"CODE_FACTORY_DATABASE_URL={URL}\nCODE_FACTORY_PORT=4103\n"
    )
    monkeypatch.setenv("CODE_FACTORY_PORT", "4999")
    _read_env_files(monkeypatch, tmp_path)
    assert load_settings().port == 4999


def test_no_env_file_present_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_NAME_VARIABLE, "dev")
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    _read_env_files(monkeypatch, tmp_path)
    assert load_settings().port == 4000


def test_a_misspelt_key_in_an_env_file_fails_loudly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env.local").write_text(
        f"CODE_FACTORY_DATABASE_URL={URL}\nCODE_FACTORY_PROT=4103\n"
    )
    _read_env_files(monkeypatch, tmp_path)
    with pytest.raises(SettingsError) as raised:
        load_settings()
    assert "CODE_FACTORY_PROT is not a setting" in str(raised.value)
    assert LEAK_MARKER not in str(raised.value)


def test_the_folders_default_under_the_users_home_and_the_environment_overrides_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = load_settings()
    assert settings.state_dir == tmp_path / ".local/state/code-factory"
    assert settings.releases_dir == tmp_path / ".local/share/code-factory/releases"
    monkeypatch.setenv("CODE_FACTORY_STATE_DIR", "/var/lib/factory")
    monkeypatch.setenv("CODE_FACTORY_RELEASES_DIR", "/srv/releases")
    settings = load_settings()
    assert (settings.state_dir, settings.releases_dir) == (
        Path("/var/lib/factory"),
        Path("/srv/releases"),
    )


@pytest.mark.parametrize("variable", ["STATE_DIR", "RELEASES_DIR", "RUN_DIR"])
def test_a_folder_setting_must_be_an_absolute_path(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    monkeypatch.setenv(f"CODE_FACTORY_{variable}", "relative/place")
    with pytest.raises(SettingsError, match=f"CODE_FACTORY_{variable} is invalid"):
        load_settings()


def test_the_run_directory_is_under_the_runtime_directory_when_there_is_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/501")
    assert load_settings().run_dir == Path("/run/user/501/code-factory")


def test_the_run_directory_falls_back_to_a_folder_named_for_the_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", None)  # tempfile caches the folder it chose first
    assert load_settings().run_dir == tmp_path / f"code-factory-{os.getuid()}"


def test_stop_at_eof_is_off_until_asked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    assert load_settings().stop_at_eof is False
    monkeypatch.setenv("CODE_FACTORY_STOP_AT_EOF", "1")
    assert load_settings().stop_at_eof is True


def test_the_broker_limits_have_their_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    settings = load_settings()
    assert (
        settings.broker_call_timeout_s,
        settings.broker_sweep_interval_s,
        settings.broker_read_timeout_s,
        settings.broker_max_body_mib,
    ) == (15.0, 30.0, 600.0, 32)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("BROKER_CALL_TIMEOUT_S", "0"),
        ("BROKER_SWEEP_INTERVAL_S", "0"),
        ("BROKER_READ_TIMEOUT_S", "0"),
        ("BROKER_CALL_TIMEOUT_S", "-1"),
        ("BROKER_MAX_BODY_MIB", "0"),
    ],
)
def test_a_broker_limit_must_be_positive(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    monkeypatch.setenv(f"CODE_FACTORY_{variable}", value)
    with pytest.raises(SettingsError, match=f"CODE_FACTORY_{variable} is invalid"):
        load_settings()


def test_settings_load_without_a_database_url_when_the_command_never_opens_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(database=False)
    assert settings.port == 4000
    monkeypatch.setenv("CODE_FACTORY_PORT", "70000")
    with pytest.raises(SettingsError, match="CODE_FACTORY_PORT is invalid"):
        load_settings(database=False)


def test_a_key_without_the_prefix_in_an_env_file_is_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text(f"CODE_FACTORY_DATABASE_URL={URL}\nEDITOR=vim\nPATH_X=1\n")
    _read_env_files(monkeypatch, tmp_path)
    assert load_settings().port == 4000


def test_a_bad_password_url_from_a_file_is_refused_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env.local").write_text(
        f"CODE_FACTORY_DATABASE_URL=postgresql://code_factory:{LEAK_MARKER}@h:5432/x\n"
    )
    _read_env_files(monkeypatch, tmp_path)
    with pytest.raises(SettingsError) as raised:
        load_settings()
    assert "the scheme must be postgresql+asyncpg" in str(raised.value)
    assert LEAK_MARKER not in str(raised.value)


def test_an_empty_runtime_directory_counts_as_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(DATABASE_URL_VARIABLE, URL)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", None)
    assert load_settings().run_dir == tmp_path / f"code-factory-{os.getuid()}"
