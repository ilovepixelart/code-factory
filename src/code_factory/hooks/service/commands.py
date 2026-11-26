"""How a hook starts: the command strings the agent settings and `install` write."""

import shlex
import sys
from pathlib import Path

from code_factory.hooks.models import HookCommands

HOOK_FILE = Path(__file__).resolve().parents[1] / "adapters" / "hook.py"
LAUNCH_FLAGS = ("-I", "-S")  # isolated, no site packages: the launcher is stdlib only


def build_commands(python: str | None = None) -> HookCommands:
    """The commands of a hook, each `<abs python> -I -S <abs launcher> <name>`.

    Never `uv run` and never an import of the package: a hook starts on every shell command of a
    run. `recall_cli` is the full `code-factory recall`, for the owner's own sessions.
    """
    interpreter = python or sys.executable
    launch = shlex.join([interpreter, *LAUNCH_FLAGS, str(HOOK_FILE)])
    installed = Path(interpreter).with_name("code-factory")
    full = (
        shlex.quote(str(installed))
        if installed.exists()
        else f"{shlex.quote(interpreter)} -m code_factory.app"
    )
    return HookCommands(
        rewrite=f"{launch} rewrite",
        tell=f"{launch} tell",
        permission=f"{launch} permission",
        recall=f"{launch} recall",
        recall_cli=f"{full} recall",
    )
