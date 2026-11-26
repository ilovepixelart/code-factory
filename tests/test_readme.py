import re
from pathlib import Path

from pydantic_core import PydanticUndefined

from code_factory.platform.config import Settings

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
QUICKSTART = (ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
ENV_PREFIX = Settings.model_config["env_prefix"]


def test_the_configuration_table_lists_every_setting_and_only_those() -> None:
    documented = set(re.findall(rf"^\| `({ENV_PREFIX}[A-Z_]+)` \|", README, flags=re.MULTILINE))
    declared = {ENV_PREFIX + name.upper() for name in Settings.model_fields}
    assert documented == declared


def test_the_configuration_table_gives_each_default() -> None:
    defaults = {
        ENV_PREFIX + name.upper(): field.default
        for name, field in Settings.model_fields.items()
        if not field.is_required()
    }
    for variable, default in defaults.items():
        row = re.search(rf"^\| `{variable}` \| `([^`]*)` \|", README, flags=re.MULTILINE)
        assert row, f"{variable} has no default in the README table"
        if default is not PydanticUndefined:  # a computed default is described, not compared
            assert row.group(1) == str(default)


def test_every_relative_link_and_image_resolves() -> None:
    targets = re.findall(r"(?:\]\(|src=\")(?!https?:|#)([^)\"#]+)", README)
    assert targets
    missing = [target for target in targets if not (ROOT / target).exists()]
    assert not missing


def test_every_internal_anchor_names_a_heading() -> None:
    headings = {
        re.sub(r"[^a-z0-9 -]", "", title.lower()).replace(" ", "-")
        for title in re.findall(r"^#+ (.+)$", README, flags=re.MULTILINE)
    }
    anchors = re.findall(r"\]\(#([^)]+)\)", README)
    assert anchors
    assert set(anchors) <= headings


def test_the_quickstart_makes_the_env_file_owner_only_before_it_holds_the_password() -> None:
    chmod = QUICKSTART.index("install -m 600 /dev/null .env.local")
    write = QUICKSTART.index("cat > .env.local")
    assert chmod < write
