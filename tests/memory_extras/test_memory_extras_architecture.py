"""Who imports memory-extras: the base memory module never does, and others only its API."""

import ast
from pathlib import Path

from repo_files import ROOT

PACKAGE = ROOT / "src" / "code_factory"
NAME = "code_factory.memory_extras"
PUBLIC = {"service", "models"}


def imported(path: Path) -> list[str]:
    """Every `code_factory.memory_extras...` module a file imports."""
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(NAME):
            found.append(str(node.module))
        elif isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.startswith(NAME)]
    return found


def importers() -> dict[Path, list[str]]:
    own = PACKAGE / "memory_extras"
    return {
        path: names
        for path in PACKAGE.rglob("*.py")
        if own not in path.parents and (names := imported(path))
    }


def test_the_base_memory_module_never_imports_memory_extras() -> None:
    assert [p for p in importers() if (PACKAGE / "memory") in p.parents] == []


def test_every_other_importer_reaches_only_the_service_and_models_or_is_the_composition_root() -> (
    None
):
    for path, names in importers().items():
        for name in names:
            leaf = name.removeprefix(NAME).strip(".").split(".")[0]
            allowed = PUBLIC | ({"module"} if path.name == "app.py" else set())
            assert leaf in allowed, f"{path.relative_to(ROOT)} imports {name}"
