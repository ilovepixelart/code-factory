"""What the tools' own files say, and how exceptions.toml must agree with them.

`deny.toml` and `pnpm-workspace.yaml` list advisories to ignore and (pnpm) packages taken under
the package age; each such item needs an entry in exceptions.toml, and each entry must still be
named by its file.
"""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from code_factory.settings.models.problems import Problem
from code_factory.settings.rules.config import TomlError, parse_toml

if TYPE_CHECKING:
    from code_factory.settings.rules.entries import ExceptionEntry

EXCEPTIONS_FILE = ".code-factory/exceptions.toml"
_EXACT = re.compile(
    r"(@[A-Za-z0-9][A-Za-z0-9._~-]*/)?[A-Za-z0-9][A-Za-z0-9._~-]*"
    r"@\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?"
)


@dataclass(frozen=True)
class Listed:
    """An ignore or an age exclusion a tool file lists, with its line."""

    file: str
    id: str
    line: int


@dataclass(frozen=True)
class ToolFiles:
    """Every ignore and age exclusion of the tracked tool files, and each file that did not read."""

    ignores: tuple[Listed, ...] = ()
    excludes: tuple[Listed, ...] = ()
    problems: tuple[Problem, ...] = ()


def is_exact(package: str) -> bool:
    """Whether `package` is `<name>@<major>.<minor>.<patch>` with an optional pre-release."""
    return _EXACT.fullmatch(package) is not None


def file_name(path: str) -> str:
    """The last component of a repository path."""
    return path.rsplit("/", 1)[-1]


def sibling(beside: str, name: str) -> str:
    """The file `name` in the folder of the repository path `beside`."""
    folder = str(PurePosixPath(beside).parent)
    return name if folder == "." else f"{folder}/{name}"


def line_holding(text: str, item: str) -> int:
    """The first line of `text` holding `item`, 0 when none does."""
    return next((n for n, line in enumerate(text.splitlines(), start=1) if item in line), 0)


def listed(file: str, text: str, ids: list[str]) -> tuple[Listed, ...]:
    """`ids` as the items `file` lists, each on the first line that holds it."""
    return tuple(Listed(file, item, line_holding(text, item)) for item in ids)


def deny_ignores(text: str) -> list[str] | str:
    """The `[advisories] ignore` items of a deny.toml, or the sentence for why it did not parse.

    An item is a string, or a table naming its `id` or `crate`.
    """
    parsed = parse_toml(text)
    if isinstance(parsed, TomlError):
        return f"toml: {parsed.message}"
    advisories = parsed.get("advisories")
    items = advisories.get("ignore") if isinstance(advisories, dict) else None
    found: list[str] = []
    for item in items if isinstance(items, list) else []:
        name = item if isinstance(item, str) else None
        if isinstance(item, dict):
            name = next((v for k in ("id", "crate") if isinstance(v := item.get(k), str)), None)
        if name is not None:
            found.append(name)
    return found


def cargo_lock_holds(text: str, package: str) -> bool:
    """Whether a Cargo.lock resolves `package` (`<name>@<version>`) at that version."""
    name, separator, version = package.rpartition("@")
    if not separator or not name:
        return False
    parsed = parse_toml(text)
    if isinstance(parsed, TomlError):
        return False
    packages = parsed.get("package")
    return isinstance(packages, list) and any(
        isinstance(p, dict) and p.get("name") == name and p.get("version") == version
        for p in packages
    )


def _missing(entry: ExceptionEntry, file: str) -> Problem:
    return Problem(EXCEPTIONS_FILE, entry.name_line, f"{entry.name} is not in {file}")


def unlisted_problems(entries: list[ExceptionEntry], tools: ToolFiles) -> list[Problem]:
    """Each ignore and age exclusion of the tool files with no entry, or no exact version."""
    found = [
        Problem(
            item.file,
            item.line,
            f"advisory ignore {item.id} has no entry in {EXCEPTIONS_FILE}",
        )
        for item in tools.ignores
        if not any(
            e.kind == "advisory" and e.name == item.id and e.file == item.file for e in entries
        )
    ]
    for item in tools.excludes:
        lockfile = sibling(item.file, "pnpm-lock.yaml")
        if not is_exact(item.id):
            why = f"minimumReleaseAgeExclude {item.id} is not one exact version <name>@<x.y.z>"
        elif any(e.kind == "age" and e.name == item.id and e.file == lockfile for e in entries):
            continue
        else:
            why = f"minimumReleaseAgeExclude {item.id} has no [[age]] entry in {EXCEPTIONS_FILE}"
        found.append(Problem(item.file, item.line, why))
    return found


def stale_problems(
    entry: ExceptionEntry, tools: ToolFiles, locked: frozenset[tuple[str, str]]
) -> list[Problem]:
    """Where the entry's own file no longer holds what the entry speaks for."""
    if entry.kind == "advisory":
        named = any(i.id == entry.name and i.file == entry.file for i in tools.ignores)
        return [] if named else [_missing(entry, entry.file)]
    found = []
    if (entry.file, entry.name) not in locked:
        found.append(_missing(entry, entry.file))
    if file_name(entry.file) == "pnpm-lock.yaml":
        workspace = sibling(entry.file, "pnpm-workspace.yaml")
        if not any(i.id == entry.name and i.file == workspace for i in tools.excludes):
            found.append(_missing(entry, workspace))
    return found


def shared_branch_problems(
    entries: list[ExceptionEntry], sharing: dict[str, tuple[str, ...]]
) -> list[Problem]:
    """Each age entry whose ticket shares its branch with another ticket."""
    return [
        Problem(
            EXCEPTIONS_FILE,
            entry.ticket_line,
            f"{entry.ticket} shares its branch with {others[0]}: a security fix under the "
            "package age lands as its own ticket",
        )
        for entry in entries
        if entry.kind == "age" and (others := sharing.get(entry.ticket)) is not None and others
    ]
