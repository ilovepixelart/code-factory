"""Review pins: the named checks a ticket's requirements cite that no test file defines."""

from collections.abc import Collection, Sequence

from code_factory.platform.text import defined_functions, python_nodes, section_rows

_SCRIPTS = ("ts", "tsx", "mts", "cts", "js", "jsx", "mjs", "cjs")
_FOLDERS = frozenset({"tests", "test", "__tests__", "e2e", "spec"})
_ACCEPTANCE = "## Acceptance criteria"
_REVIEW = "review"


def patterns(field: str) -> list[str]:
    """A field's comma-separated patterns, blanks dropped."""
    return [part.strip() for part in field.split(",") if part.strip()]


def is_test_file(path: str) -> bool:
    """Whether `path`, relative to the repository, is a test by its name or its folder.

    By name: `*.test.<script>`, `*.spec.<script>`, `test_*.py`, `*_test.py`, `*_test.go`; by
    folder: any file under `tests`, `test`, `__tests__`, `e2e` or `spec`. Case is folded.
    """
    *folders, name = path.lower().split("/")
    stem, _, extension = name.rpartition(".")
    if not stem:
        stem, extension = name, ""
    kind = stem.rpartition(".")[2] if "." in stem else ""
    script = extension in _SCRIPTS and kind in {"test", "spec"}
    pytest_file = extension == "py" and (stem.startswith("test_") or stem.endswith("_test"))
    go = extension == "go" and stem.endswith("_test")
    return script or pytest_file or go or any(part in _FOLDERS for part in folders)


def check_nodes(path: str, text: str) -> list[tuple[str, str]]:
    """Each test a file defines as `(name, node)`; nothing for a file no runner reads."""
    if path.endswith(".py"):
        return python_nodes(text)
    script = any(path.endswith((f".test.{ext}", f".spec.{ext}")) for ext in _SCRIPTS)
    if path.endswith((".rs", "_test.go")) or script:
        return [(name, name) for name in defined_functions(text)]
    return []


def named_checks(requirements: str) -> list[tuple[str, list[str]]]:
    """Each acceptance criterion's id with the checks its last column names."""
    found = []
    for row in section_rows(requirements, _ACCEPTANCE):
        if len(row.cells) < 2:  # noqa: PLR2004  # an id and a named-check column
            continue
        names = [cell.strip().strip("`") for cell in row.cells[-1].split(",")]
        found.append((row.cells[0], [name for name in names if name]))
    return found


def unresolved_checks(
    requirements: Sequence[tuple[str, Sequence[str]]], defined: Collection[str]
) -> list[str]:
    """`<id>: <name>` for every named check no test defines, and `<id>: no named check`."""
    missing = []
    for requirement, names in requirements:
        if not names:
            missing.append(f"{requirement}: no named check")
        missing.extend(
            f"{requirement}: {name}"
            for name in names
            if name.lower() != _REVIEW and name not in defined
        )
    return missing
