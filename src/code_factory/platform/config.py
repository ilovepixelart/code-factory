"""Settings read from `CODE_FACTORY_*` environment variables."""

import os
import re
import tempfile
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from code_factory.platform.errors import SettingsError

DATABASE_URL_VARIABLE = "CODE_FACTORY_DATABASE_URL"
ENV_NAME_VARIABLE = "CODE_FACTORY_ENV"
_DATABASE_SCHEME = "postgresql+asyncpg"
_ENV_NAME = re.compile(r"[A-Za-z0-9_-]+")
_URL_HINT = (
    f"Set {DATABASE_URL_VARIABLE} to a postgresql+asyncpg:// URL, for example: "
    f'export {DATABASE_URL_VARIABLE}="postgresql+asyncpg://code_factory:'
    "$(security find-generic-password -a code_factory -s code-factory-postgres -w)"
    '@127.0.0.1:5432/code_factory"'
)


# `load_settings(database=False)` only: nothing reads it, and the unit of work it leads to refuses
# every use, so a command that never opens the database cannot reach it by accident.
NO_DATABASE_URL = "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused"


def _env_files() -> tuple[str, ...]:
    """The env files, lowest priority first: `.env`, `.env.{CODE_FACTORY_ENV}`, `.env.local`.

    Relative paths, so they are read from the working directory. The name is a path segment, so
    anything but letters, digits, dashes and underscores is refused.
    """
    files = [".env"]
    name = os.environ.get(ENV_NAME_VARIABLE, "")  # empty counts as unset
    if name:
        if not _ENV_NAME.fullmatch(name):
            msg = f"{ENV_NAME_VARIABLE} must hold only letters, digits, dashes and underscores"
            raise SettingsError(msg)
        files.append(f".env.{name}")
    files.append(".env.local")
    return tuple(files)


_UNPARSEABLE = "the database URL cannot be parsed"
_UNENCODED_AT = "the password holds an unencoded @; percent-encode it as %40"


def parse_database_url(raw: str) -> URL:
    """Parse like the driver, or raise a `ValueError` whose message holds no part of `raw`.

    A password with an unencoded `@` makes the parse ambiguous: SQLAlchemy ends the password at the
    first `@`, so the rest lands in the host, port, database or query. Those are refused, and
    every failure of the parser (`ArgumentError`, `ValueError`, `TypeError`: their messages quote
    the URL) becomes one fixed sentence.
    """
    authority = raw.partition("://")[2].partition("/")[0]
    if authority.count("@") > 1:
        raise ValueError(_UNENCODED_AT)
    try:
        url = make_url(raw)
    except ArgumentError, ValueError, TypeError:
        raise ValueError(_UNPARSEABLE) from None
    spill = (url.host, url.database, *url.query, *map(str, url.query.values()))
    if any("@" in part for part in spill if part is not None):
        raise ValueError(_UNENCODED_AT)
    return url


def _state_dir() -> Path:
    return Path.home() / ".local/state/code-factory"


def _releases_dir() -> Path:
    return Path.home() / ".local/share/code-factory/releases"


def _run_dir() -> Path:
    """Sockets and logs of a served board: not state, so a runtime directory, not `state_dir`."""
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime:
        return Path(runtime) / "code-factory"
    # The user's own temporary folder (`TMPDIR`), not a name others could take first in `/tmp`.
    return Path(tempfile.gettempdir()) / f"code-factory-{os.getuid()}"


class Settings(BaseSettings):
    """Process configuration. The database password never leaves `SecretStr`."""

    # `extra="forbid"` with `dotenv_filtering="match_prefix"`: a CODE_FACTORY_ key in an env file
    # that is no setting fails, one without the prefix is ignored. The process environment is never
    # checked for strays (other CODE_FACTORY_ variables live there).
    model_config = SettingsConfigDict(
        env_prefix="CODE_FACTORY_",
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="forbid",
        dotenv_filtering="match_prefix",
    )

    database_url: SecretStr
    host: str = "127.0.0.1"
    port: Annotated[int, Field(ge=0, le=65535)] = 4000  # 0: a free port, printed at start
    log_level: str = "INFO"
    open: bool = True  # `serve` opens the browser signed in, on a terminal
    # The schema every table lives in: a second one gives the browser tests a copy of their own.
    db_schema: Annotated[str, Field(pattern=r"^[a-z_][a-z0-9_]{0,62}$")] = "public"
    db_pool_size: Annotated[int, Field(ge=1)] = 10
    db_max_overflow: Annotated[int, Field(ge=0)] = 5
    db_pool_timeout_s: Annotated[float, Field(gt=0)] = 10.0
    db_pool_recycle_s: Annotated[int, Field(ge=1)] = 1800
    ready_timeout_s: Annotated[float, Field(gt=0)] = 2.0
    schema_check_timeout_s: Annotated[float, Field(gt=0)] = 5.0
    shutdown_timeout_s: Annotated[int, Field(ge=1)] = 10
    # Files that are not in the database: run logs, the session spool, check logs and caches.
    state_dir: Path = Field(default_factory=_state_dir)
    releases_dir: Path = Field(default_factory=_releases_dir)
    run_dir: Path = Field(default_factory=_run_dir)
    # End the served board when its standard input closes, for a parent that owns its life.
    stop_at_eof: bool = False
    broker_call_timeout_s: Annotated[float, Field(gt=0)] = 15.0
    broker_sweep_interval_s: Annotated[float, Field(gt=0)] = 30.0
    broker_read_timeout_s: Annotated[float, Field(gt=0)] = 600.0
    broker_max_body_mib: Annotated[int, Field(ge=1)] = 32

    @field_validator("state_dir", "releases_dir", "run_dir")
    @classmethod
    def _absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            msg = "must be an absolute path"
            raise ValueError(msg)
        return value

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, value: SecretStr) -> SecretStr:
        # The messages must not echo the value: it can hold the password.
        url = parse_database_url(value.get_secret_value())
        if url.drivername != _DATABASE_SCHEME:
            msg = f"the scheme must be {_DATABASE_SCHEME}"
            raise ValueError(msg)
        return value

    @field_validator("log_level")
    @classmethod
    def _log_level(cls, value: str) -> str:
        upper = value.upper()
        if upper not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            msg = "must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL"
            raise ValueError(msg)
        return upper

    @property
    def advertised_host(self) -> str:
        """The client address for this listener. Compose publishes the wildcard on loopback."""
        return "127.0.0.1" if self.host == "0.0.0.0" else self.host  # noqa: S104

    @property
    def base_url(self) -> str:
        """Where the server is reached: an IPv6 literal is bracketed."""
        advertised = self.advertised_host
        host = f"[{advertised}]" if ":" in advertised else advertised
        return f"http://{host}:{self.port}"

    @property
    def database_target(self) -> str:
        """The database as `host:port/name` (port when given), safe to print.

        Built from the parsed URL's host, port and database only, parsed the way the driver does.
        """
        try:
            url = parse_database_url(self.database_url.get_secret_value())
        except ValueError:
            raise SettingsError(_UNPARSEABLE) from None
        host = f"{url.host}:{url.port}" if url.port is not None else url.host
        return f"{host}/{url.database}"


def load_settings(*, database: bool = True) -> Settings:
    """Build `Settings`, turning a validation failure into one sentence.

    `database=False` is for a command that never opens the database (it may run before any exists):
    the URL is not required and the one in the environment is ignored.

    Pydantic's own message repeats the offending input, which for the database URL holds the
    password, so the sentence is built from the field names and messages only.
    """
    try:
        return Settings() if database else Settings(database_url=SecretStr(NO_DATABASE_URL))
    except ValidationError as error:
        problems = []
        for item in error.errors(include_input=False, include_url=False):
            name = str(item["loc"][0]) if item["loc"] else "settings"
            if name == "database_url" and item["type"] == "missing":
                problems.append(f"{DATABASE_URL_VARIABLE} is not set. {_URL_HINT}")
            elif name == "database_url":
                problems.append(f"{DATABASE_URL_VARIABLE} is invalid: {item['msg']}. {_URL_HINT}")
            elif item["type"] == "extra_forbidden":
                problems.append(f"CODE_FACTORY_{name.upper()} is not a setting")
            else:
                problems.append(f"CODE_FACTORY_{name.upper()} is invalid: {item['msg']}")
        raise SettingsError(" ".join(problems)) from None
