"""The talk module sits below tickets: it imports the platform and nothing of another module."""

import ast
from pathlib import Path

from repo_files import ROOT

TALK = ROOT / "src" / "code_factory" / "talk"


def imported_packages(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def test_talk_imports_no_other_module() -> None:
    others = {
        f"{path}: {name}"
        for path in TALK.rglob("*.py")
        for name in imported_packages(path)
        if name.startswith("code_factory.") and name.split(".")[1] not in {"talk", "platform"}
    }
    assert others == set()
