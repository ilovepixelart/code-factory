"""The factory reads other modules only through ports: its code imports `platform` and itself."""

import ast
from pathlib import Path

from repo_files import ROOT

FACTORY = ROOT / "src" / "code_factory" / "factory"
ALLOWED = ("code_factory.factory", "code_factory.platform")


def imported_from_the_package(source: str) -> set[str]:
    """Every `code_factory.*` module a source file imports."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return {name for name in found if name == "code_factory" or name.startswith("code_factory.")}


def foreign(path: Path) -> list[str]:
    return sorted(
        name
        for name in imported_from_the_package(path.read_text(encoding="utf-8"))
        if not name.startswith(ALLOWED)
    )


def test_the_scan_names_an_import_of_another_module() -> None:
    source = "from code_factory.runs.service import RunService\nimport code_factory.tickets.rules\n"
    assert imported_from_the_package(source) == {
        "code_factory.runs.service",
        "code_factory.tickets.rules",
    }


def test_the_scan_lets_platform_and_the_package_itself_through() -> None:
    source = (
        "from code_factory.platform.errors import BadRequestError\n"
        "from code_factory.factory.models import Dashboard\n"
    )
    assert [n for n in imported_from_the_package(source) if not n.startswith(ALLOWED)] == []


def test_no_factory_file_imports_another_module() -> None:
    offenders = {
        str(p.relative_to(FACTORY)): foreign(p) for p in FACTORY.rglob("*.py") if foreign(p)
    }
    assert offenders == {}
