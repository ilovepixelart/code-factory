"""What exceptions.toml speaks for, read from the repository: tool files, lockfiles and tests."""

from pathlib import Path

from code_factory.settings.adapters.files import Files
from code_factory.settings.adapters.git import GitFacts
from code_factory.settings.adapters.parsing import (
    YAML_BYTES,
    in_thread,
    lock_packages,
    workspace_lists,
)
from code_factory.settings.models.problems import Problem
from code_factory.settings.rules.entries import ExceptionEntry
from code_factory.settings.rules.quarantine import definition_search
from code_factory.settings.rules.templates import CONFIG_BYTES, unreadable_message
from code_factory.settings.rules.tool_files import (
    EXCEPTIONS_FILE,
    Listed,
    ToolFiles,
    cargo_lock_holds,
    deny_ignores,
    file_name,
    listed,
)

_CARGO_LOCK = "Cargo.lock"

TOOL_FILES = ("**/deny.toml", "**/pnpm-workspace.yaml")
CARGO_LOCK_BYTES = 8 * 1024 * 1024
UNPARSED_YAML = "yaml: not valid YAML, or too large to read"


class Sources:
    """Reads the files and tests an exception entry names."""

    def __init__(self, files: Files, git: GitFacts) -> None:
        self._files = files
        self._git = git

    async def tool_files(self, root: Path) -> ToolFiles:
        """The ignores and age exclusions of the tracked tool files, and each that did not read."""
        ignores: list[Listed] = []
        excludes: list[Listed] = []
        problems: list[Problem] = []
        for file in await self._git.tracked(root, list(TOOL_FILES)):
            text = await self._files.read_below(root, file, CONFIG_BYTES)
            if text is None:
                problems.append(Problem(file, 0, unreadable_message(CONFIG_BYTES)))
            elif file_name(file) == "deny.toml":
                found = deny_ignores(text)
                if isinstance(found, str):
                    problems.append(Problem(file, 0, found))
                else:
                    ignores += listed(file, text, found)
            elif (workspace := await workspace_lists(text)) is None:
                problems.append(Problem(file, 0, UNPARSED_YAML))
            else:
                ignores += listed(file, text, workspace.ignores)
                excludes += listed(file, text, workspace.excludes)
        return ToolFiles(tuple(ignores), tuple(excludes), tuple(problems))

    async def _lock_holds(self, root: Path, entry: ExceptionEntry) -> bool | Problem:
        """Whether the entry's lockfile resolves its package, or why that cannot be said."""
        name = file_name(entry.file)
        limit = CARGO_LOCK_BYTES if name == _CARGO_LOCK else YAML_BYTES
        text = await self._files.read_below(root, entry.file, limit)
        if text is None:
            if not await self._files.present(root, entry.file):
                return False
            return Problem(
                EXCEPTIONS_FILE, entry.name_line, f"{entry.file} {unreadable_message(limit)}"
            )
        if name == _CARGO_LOCK:
            return await in_thread(cargo_lock_holds, text, entry.name) is True
        packages = await lock_packages(text)
        if packages is None:
            return Problem(entry.file, 0, UNPARSED_YAML)
        return entry.name in packages

    async def locked(
        self, root: Path, entries: list[ExceptionEntry]
    ) -> tuple[frozenset[tuple[str, str]], list[Problem]]:
        """The `(lockfile, package)` pairs the age entries' lockfiles resolve, and the problems.

        The problems name each lockfile that is present but cannot be read, once. An unreadable one
        counts as holding, so the entry is not also reported as missing from it.
        """
        held: set[tuple[str, str]] = set()
        problems: dict[tuple[str, int, str], Problem] = {}
        for entry in (e for e in entries if e.kind == "age"):
            if file_name(entry.file) not in {_CARGO_LOCK, "pnpm-lock.yaml"}:
                continue
            result = await self._lock_holds(root, entry)
            if isinstance(result, Problem):
                problems[(result.path, result.line, result.message)] = result
                held.add((entry.file, entry.name))
            elif result:
                held.add((entry.file, entry.name))
        return frozenset(held), list(problems.values())

    async def tests(self, root: Path, entries: list[ExceptionEntry]) -> dict[str, bool]:
        """Whether each quarantined test is defined in a tracked file."""
        found = {}
        for entry in (e for e in entries if e.kind == "quarantine"):
            pattern, paths = definition_search(entry.name)
            found[entry.name] = await self._git.grep_exists(root, pattern, paths)
        return found
