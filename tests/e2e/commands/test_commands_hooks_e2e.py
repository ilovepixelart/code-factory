"""Installing the board's hooks into a Claude Code settings file."""

import json
import os
import subprocess
import sys
from pathlib import Path

EVENTS = (
    "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
    "PostToolUseFailure", "PermissionRequest", "Notification", "SubagentStart", "SubagentStop",
    "Stop",
)  # fmt: skip


def test_install_runs_without_a_database_and_writes_the_users_settings(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CODE_FACTORY_")}
    env["HOME"] = str(tmp_path)
    run = subprocess.run(  # the program under test, fixed arguments
        [sys.executable, "-m", "code_factory.app", "install"],
        env=env, capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip

    settings = tmp_path / ".claude" / "settings.json"
    assert run.returncode == 0, run.stderr
    assert run.stdout == f"installed capture hooks in {settings}\n"
    hooks = json.loads(settings.read_text())["hooks"]
    assert set(hooks) == set(EVENTS)
    assert hooks["PreToolUse"][-1]["matcher"] == "Bash"
