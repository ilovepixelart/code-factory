"""Architecture guard: runs import-linter as part of the test suite, and closes its gaps.

The contracts live in `pyproject.toml` under `[tool.importlinter]` and are explained in
docs/architecture.md. Import-linter only checks what a contract names, so the other tests here
fail when a package or a file would sit outside every contract.
"""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from importlinter.api import use_cases

from repo_files import ROOT

PACKAGE = ROOT / "src" / "code_factory"
KERNEL = "platform"
# The file roles of a module (a package of the same name holds a role that outgrew one file).
LAYER_NAMES = {
    "module", "routes", "tools", "cli", "service", "adapters", "repository", "ports", "tables",
    "rules", "models",
}  # fmt: skip


def modules_in_the_layers_contract() -> set[str]:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = {c["name"]: c for c in config["tool"]["importlinter"]["contracts"]}
    return {name.removeprefix("code_factory.") for name in contracts["module-layers"]["containers"]}


def modules_with_tables(package: Path) -> list[str]:
    """Modules whose tables are one file or a package that outgrew it."""
    return sorted(
        path.name
        for path in package.iterdir()
        if (path / "tables.py").is_file() or (path / "tables" / "__init__.py").is_file()
    )


def test_a_module_that_split_its_tables_into_a_package_is_still_found(tmp_path: Path) -> None:
    for name, tables in {
        "one": "tables.py",
        "split": "tables/__init__.py",
        "none": "service.py",
    }.items():
        target = tmp_path / name / tables
        target.parent.mkdir(parents=True)
        target.touch()
    assert modules_with_tables(tmp_path) == ["one", "split"]


def module_packages() -> set[str]:
    return {
        path.name
        for path in PACKAGE.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file() and path.name != KERNEL
    }


@pytest.mark.timeout(60)
def test_import_contracts_hold() -> None:
    exit_code = use_cases.lint_imports(config_filename=str(ROOT / "pyproject.toml"))
    if exit_code != use_cases.SUCCESS:
        pytest.fail("import-linter contract violation: run `uv run lint-imports` for the report.")


def test_every_package_under_code_factory_is_a_listed_module_or_the_platform() -> None:
    unlisted = module_packages() - modules_in_the_layers_contract()
    assert not unlisted, (
        f"{sorted(unlisted)} sit outside the layering: add each to `containers` of the "
        "`module-layers` contract in pyproject.toml"
    )


def test_every_listed_module_exists() -> None:
    missing = modules_in_the_layers_contract() - module_packages()
    assert not missing, f"`module-layers` lists {sorted(missing)}, which are not packages"


def is_stray(path: Path) -> bool:
    if path.is_dir():
        return path.name not in LAYER_NAMES | {"__pycache__"}
    return path.suffix == ".py" and path.stem not in LAYER_NAMES | {"__init__"}


def test_every_file_of_a_module_has_a_layer_name() -> None:
    stray = sorted(
        str(path.relative_to(PACKAGE))
        for module in module_packages()
        for path in (PACKAGE / module).iterdir()
        if is_stray(path)
    )
    assert not stray, (
        f"{stray} have no layer name ({sorted(LAYER_NAMES)}), so no layering contract applies; "
        "rename the file or make it part of one of those"
    )


def test_importing_the_composition_root_registers_every_modules_tables() -> None:
    with_tables = [m for m in modules_with_tables(PACKAGE) if m in module_packages()]
    probe = (
        "import sys, code_factory.app\n"
        f"names = {with_tables!r}\n"
        "missing = [m for m in names if f'code_factory.{m}.tables' not in sys.modules]\n"
        "sys.exit(','.join(missing) or 0)"
    )
    result = subprocess.run(  # noqa: S603  # our own interpreter, a fixed program
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False, cwd=Path(ROOT)
    )
    assert result.returncode == 0, (
        f"`code_factory.app` does not import the tables of {result.stderr.strip()}: Alembic "
        "would not see them; import each module's `module.py` (which imports its tables)"
    )
