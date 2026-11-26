"""What the broker module never does: write the environment, print, or log a secret-shaped value."""

import ast
from pathlib import Path

from repo_files import ROOT

BROKER = ROOT / "src" / "code_factory" / "broker"


def sources() -> list[tuple[Path, ast.Module]]:
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in BROKER.rglob("*.py")]


def test_there_are_sources_to_scan() -> None:
    assert len(sources()) > 15


def test_no_file_prints() -> None:
    printed = [
        f"{path.name}:{node.lineno}"
        for path, tree in sources()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]
    assert printed == []


def test_no_file_writes_the_process_environment() -> None:
    writes = [
        f"{path.name}:{node.lineno}"
        for path, tree in sources()
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in {"environ", "putenv", "setenv"}
    ]
    assert writes == []


def test_no_log_call_takes_a_secret_value() -> None:
    """A log call's arguments are fixed text and ids: none unwraps a secret."""
    levels = {"debug", "info", "warning", "error", "exception", "critical"}
    offenders = [
        f"{path.name}:{node.lineno}"
        for path, tree in sources()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in levels
        and "get_secret_value" in ast.dump(node)
    ]
    assert offenders == []


def test_a_secret_is_unwrapped_only_where_it_goes_into_a_header() -> None:
    allowed = {"provider.py", "forwarding.py", "scrub.py"}
    unwrapping = {
        path.name
        for path, tree in sources()
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "get_secret_value"
    }
    assert unwrapping <= allowed
