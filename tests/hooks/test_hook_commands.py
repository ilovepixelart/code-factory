"""The command strings the agent settings write: one definition of how a hook starts."""

import ast
import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

import code_factory.hooks.adapters.hook as hook_module
from code_factory.hooks.service import HookService
from code_factory.hooks.service.commands import build_commands
from hooks_support import BRANCH, GOLDEN, bash, ticket_tree

RULES = Path(hook_module.__file__).parents[1] / "rules"
LAUNCHER_FILES = [
    Path(hook_module.__file__),
    RULES / "rewrite_guard.py",
    RULES / "shell.py",
    RULES / "git_words.py",
    RULES / "output.py",
]
HEAVY = {"asyncio", "ssl", "urllib", "http", "re", "typing", "dataclasses", "enum", "pathlib"}


def imported(path: Path, *, top_level_only: bool) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = tree.body if top_level_only else list(ast.walk(tree))
    found: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            found.add(node.module)
    return found


@pytest.mark.parametrize("path", LAUNCHER_FILES, ids=lambda p: p.name)
def test_the_launcher_files_import_only_the_standard_library_and_each_other(path: Path) -> None:
    allowed = set(sys.stdlib_module_names) | {"code_factory.hooks.rules"}

    outside = {
        name
        for name in imported(path, top_level_only=False)
        if name not in allowed and name.split(".")[0] not in allowed
    }

    assert outside == set()


@pytest.mark.parametrize("path", LAUNCHER_FILES, ids=lambda p: p.name)
def test_nothing_that_costs_start_time_is_imported_at_the_top_of_a_launcher_file(
    path: Path,
) -> None:
    top = {name.split(".")[0] for name in imported(path, top_level_only=True)}
    # `output` is loaded only after the launcher has `json` already, to print a refusal.
    costly = (
        HEAVY
        | {"socket", "subprocess", "os", "time"}
        | (set() if path.name == "output.py" else {"json"})
    )

    assert top & costly == set()


def test_the_commands_start_the_launcher_by_absolute_path_with_isolated_python() -> None:
    commands = build_commands()

    for name in ("rewrite", "tell", "permission", "recall"):
        words = shlex.split(getattr(commands, name))
        assert words == [sys.executable, "-I", "-S", str(Path(hook_module.__file__)), name]
        assert Path(words[0]).is_absolute()
        assert Path(words[3]).is_absolute()
        assert Path(words[3]).is_file()


def test_the_owners_recall_is_the_full_command_by_absolute_path() -> None:
    words = shlex.split(build_commands().recall_cli)

    assert words[-1] == "recall"
    assert Path(words[0]).is_absolute()
    assert Path(words[0]).exists()
    assert "code-factory" in words[0] or "-m" in words


def test_a_path_with_a_space_is_quoted() -> None:
    commands = build_commands(python="/opt/my python/bin/python3")

    assert shlex.split(commands.rewrite)[0] == "/opt/my python/bin/python3"
    assert commands.rewrite.startswith("'/opt/my python/bin/python3' -I -S ")


def test_the_service_hands_out_the_commands_it_was_given_or_the_default() -> None:
    from hooks_fakes import Fakes  # noqa: PLC0415

    default = Fakes().service().hook_commands()
    given = Fakes().service(commands=build_commands(python="/x/python")).hook_commands()

    assert default == build_commands()
    assert shlex.split(given.tell)[0] == "/x/python"
    assert isinstance(Fakes().service(), HookService)


def test_the_rewrite_command_runs_from_a_clean_folder_and_denies_as_the_golden_does(
    tmp_path: Path,
) -> None:
    tree = ticket_tree(tmp_path / "work").tree
    clean = tmp_path / "clean"
    clean.mkdir()
    command = build_commands().rewrite

    ran = subprocess.run(  # noqa: S603  # the command string under test, split like a runtime does
        shlex.split(command),
        input=bash("git commit --amend", tree).encode(),
        capture_output=True,
        cwd=clean,
        check=False,
        timeout=20,
    )

    assert ran.returncode == 0
    assert ran.stdout.decode() == (GOLDEN / "rewrite_denied.json").read_text(encoding="utf-8")
    assert json.loads(ran.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert BRANCH in ran.stdout.decode()
