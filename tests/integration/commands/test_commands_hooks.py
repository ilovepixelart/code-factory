"""Installing the board's hooks into a Claude Code settings file."""

import json
from pathlib import Path
from typing import Any

import pytest

from code_factory.commands.adapters import SettingsFile
from code_factory.commands.rules import add_hooks, owns, remove_hooks
from code_factory.commands.service import hook_entries
from code_factory.platform.errors import BadRequestError, ConflictError

GOLDEN = json.loads(
    (Path(__file__).parents[2] / "support/golden/formats/commands/settings.json").read_text()
)
EVENTS = (
    "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
    "PostToolUseFailure", "PermissionRequest", "Notification", "SubagentStart", "SubagentStop",
    "Stop",
)  # fmt: skip
ENTRIES = hook_entries("{capture}", EVENTS, "{recall}", "{guard}")
GUARD = {"hooks": [{"type": "command", "command": "{guard}", "timeout": 30}], "matcher": "Bash"}


def _now_designed(golden_text: str) -> dict[str, Any]:
    """The previous golden with the two documented changes: async capture, the Bash guard."""
    settings = json.loads(golden_text)
    for items in settings.get("hooks", {}).values():
        for item in items:
            for hook in item["hooks"]:
                if hook["command"] == "{capture}":
                    hook["async"] = True
    if "hooks" in settings:
        settings["hooks"]["PreToolUse"].append(GUARD)
    return settings


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=[c["name"] for c in GOLDEN["cases"]])
def test_install_writes_the_golden_settings_as_now_designed(case: dict[str, Any]) -> None:
    expected = _now_designed(GOLDEN["expected"][case["name"]]["installed"])
    assert add_hooks(case["before"] or {}, ENTRIES) == expected


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=[c["name"] for c in GOLDEN["cases"]])
def test_uninstall_leaves_the_golden_rest(case: dict[str, Any]) -> None:
    installed = add_hooks(case["before"] or {}, ENTRIES)
    expected = json.loads(GOLDEN["expected"][case["name"]]["uninstalled"])
    assert remove_hooks(installed, ENTRIES) == expected


def test_a_second_install_changes_nothing() -> None:
    once = add_hooks({}, ENTRIES)
    assert add_hooks(once, ENTRIES) is None
    assert remove_hooks({}, ENTRIES) is None


def test_an_event_that_is_not_a_list_is_left_in_place_on_uninstall() -> None:
    settings = {"hooks": {"Custom": "keep"}}
    assert remove_hooks(settings, ENTRIES) is None
    installed = add_hooks(settings, ENTRIES)
    assert installed is not None
    removed = remove_hooks(installed, ENTRIES)
    assert removed == settings


def test_hooks_that_are_not_an_object_are_refused() -> None:
    with pytest.raises(BadRequestError, match="is not an object"):
        add_hooks({"hooks": []}, ENTRIES)
    with pytest.raises(BadRequestError, match="no JSON object"):
        add_hooks([], ENTRIES)


def test_a_moved_interpreter_is_the_same_hook_but_another_tools_script_is_not() -> None:
    wanted = "/new/bin/python -I -S /x/site-packages/code_factory/sessions/rules/capture.py"
    assert owns("/old/bin/python -I -S /y/code_factory/sessions/rules/capture.py", wanted)
    assert not owns("/old/bin/python /y/other_tool/capture.py", wanted)
    assert not owns("other-tool", wanted)


async def test_an_existing_file_is_backed_up_and_a_changed_one_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"model": "opus"}\n')
    file = SettingsFile(path)
    await file.load()

    backup = await file.replace({"model": "opus", "hooks": {}})

    assert backup is not None
    assert backup.read_text() == '{"model": "opus"}\n'
    stale = SettingsFile(path)
    await stale.load()
    path.write_text('{"model": "sonnet"}\n')
    with pytest.raises(ConflictError, match="changed while it was being edited"):
        await stale.replace({})
    assert json.loads(path.read_text()) == {"model": "sonnet"}
