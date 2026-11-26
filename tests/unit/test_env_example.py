"""`.env.example` lists every setting with its default, so it cannot drift from `Settings`."""

import re
from pathlib import Path

from code_factory.platform.config import Settings

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
ENV_PREFIX = Settings.model_config["env_prefix"]
# The password in the example is a placeholder; the real one lives in the keychain.
PLACEHOLDER_URL = "postgresql+asyncpg://code_factory:change-me@127.0.0.1:5432/code_factory"


def _assignments() -> dict[str, str]:
    """The `KEY=value` lines, commented out or not, of the example."""
    lines = re.findall(r"^#? ?(CODE_FACTORY_[A-Z_]+)=(.*)$", EXAMPLE, flags=re.MULTILINE)
    return dict(lines)


def test_the_example_lists_every_setting_and_only_those() -> None:
    declared = {ENV_PREFIX + name.upper() for name in Settings.model_fields}
    assert set(_assignments()) == declared


def test_the_example_gives_each_default() -> None:
    assignments = _assignments()
    for name, field in Settings.model_fields.items():
        # A default computed from the machine (a directory) has no fixed value to pin.
        if not field.is_required() and field.default_factory is None:
            assert assignments[ENV_PREFIX + name.upper()] == str(field.default)


def test_the_example_shows_the_database_url_with_a_placeholder_password() -> None:
    assert _assignments()["CODE_FACTORY_DATABASE_URL"] == PLACEHOLDER_URL
    assert "keychain" in EXAMPLE


def test_every_setting_in_the_example_has_a_comment_line_above_it() -> None:
    lines = EXAMPLE.splitlines()
    for index, line in enumerate(lines):
        if re.match(r"^#? ?CODE_FACTORY_[A-Z_]+=", line):
            assert index > 0
            assert lines[index - 1].startswith("# ")
            assert not re.match(r"^#? ?CODE_FACTORY_", lines[index - 1])
