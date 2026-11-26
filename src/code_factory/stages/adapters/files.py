"""The test files a ticket names, read from a worktree.

A pattern may not start with `/` or hold a `..` part, and only a path that exists and whose
resolved path is inside the resolved root counts, so no pattern tells whether a file outside the
repository exists. The reads run in a worker thread with a limiter of their own and a time limit.
"""

import asyncio
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import anyio
import anyio.to_thread

from code_factory.stages.rules import CONFIG_FILE

FILE_LIMIT = 1024 * 1024
TIMEOUT_S = 10.0
MATCH_LIMIT = 10_000
_limiter = anyio.CapacityLimiter(4)


@dataclass(frozen=True)
class TestSources:
    """The patterns that matched no file, and the text of the files the others matched."""

    __test__ = False

    unmatched: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)


def _refused(pattern: str) -> bool:
    return pattern.startswith("/") or ".." in pattern.split("/")


def _inside(root: Path, found: str) -> Path | None:
    try:
        resolved = (root / found).resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_relative_to(root) else None


def _read(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            return handle.read(FILE_LIMIT).decode("utf-8", errors="replace")
    except OSError:
        return None


def _walked(root: Path, pattern: str, deadline: float) -> list[str]:
    """The files under `root` matching a `**` pattern, walking no link and stopping at the deadline.

    A glob yields only its matches, so one that matches nothing never reaches a deadline check.
    """
    found: list[str] = []
    for folder, _, names in os.walk(root):
        if time.monotonic() > deadline or len(found) >= MATCH_LIMIT:
            break
        base = Path(folder).relative_to(root)
        found.extend(str(base / name) for name in names if (base / name).full_match(pattern))
    return found[:MATCH_LIMIT]


def _globbed(root: Path, pattern: str, deadline: float) -> list[str]:
    found: list[str] = []
    for path in root.glob(pattern, recurse_symlinks=False):
        if time.monotonic() > deadline or len(found) >= MATCH_LIMIT:
            break
        found.append(str(path.relative_to(root)))
    return found


def _matches(root: Path, pattern: str, deadline: float) -> list[str]:
    """The files `pattern` names under `root`.

    A `**` does not cross a link, and the scan stops at the deadline or at `MATCH_LIMIT` matches.
    """
    if _refused(pattern):
        return []
    try:
        if "**" in pattern:
            return _walked(root, pattern, deadline)
        return _globbed(root, pattern, deadline)
    except ValueError, OSError:
        return []


def _scan(root: Path, patterns: Sequence[str]) -> TestSources:
    resolved = root.resolve()
    deadline = time.monotonic() + TIMEOUT_S
    unmatched: list[str] = []
    files: dict[str, str] = {}
    for pattern in patterns:
        inside = [
            (found, path)
            for found in _matches(resolved, pattern, deadline)
            if (path := _inside(resolved, found)) is not None and path.is_file()
        ]
        if not inside:
            unmatched.append(pattern)
        for found, path in inside:
            if time.monotonic() > deadline:
                break
            text = _read(path)
            if text is not None:
                files[found] = text
    return TestSources(unmatched, files)


def _config_text(root: Path) -> str | None:
    """The config file's text; `None` when there is none."""
    try:
        return (root / CONFIG_FILE).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    except OSError:
        return "?"


def _config_has_content(root: Path) -> bool:
    text = _config_text(root)
    return text is not None and any(
        line.strip() and not line.strip().startswith("#") for line in text.splitlines()
    )


async def config_has_content(root: Path) -> bool:
    """Whether the repository has a config file that says something, or one that cannot be read."""
    try:
        async with asyncio.timeout(TIMEOUT_S):
            return await anyio.to_thread.run_sync(
                _config_has_content, root, limiter=_limiter, abandon_on_cancel=True
            )
    except TimeoutError:
        return True


class TestFiles:
    """Expands a ticket's `tests` and `e2e` patterns inside a worktree."""

    __test__ = False

    def __init__(self, root: Path) -> None:
        self._root = root

    async def read(self, patterns: Sequence[str]) -> TestSources:
        """What the patterns match; an empty answer when the scan outlasts its time limit."""
        try:
            async with asyncio.timeout(TIMEOUT_S):
                return await anyio.to_thread.run_sync(
                    _scan, self._root, patterns, limiter=_limiter, abandon_on_cancel=True
                )
        except TimeoutError:
            return TestSources(unmatched=list(patterns))
