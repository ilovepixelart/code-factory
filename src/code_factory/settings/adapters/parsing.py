"""Parsing at the edge: `pnpm-workspace.yaml`, `pnpm-lock.yaml` and lockfiles, in worker threads.

`safe_load` builds no object a tag names. A parse runs under its own limiter and takes at most
`TIMEOUT_S`; YAML text is read up to 2 MiB.
"""

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from weakref import WeakKeyDictionary

import anyio
import yaml
from anyio import CapacityLimiter, to_thread

YAML_BYTES = 2 * 1024 * 1024
TIMEOUT_S = 10.0
LIMITER_SLOTS = 2
_limiters: WeakKeyDictionary[asyncio.AbstractEventLoop, CapacityLimiter] = WeakKeyDictionary()


@dataclass(frozen=True)
class Workspace:
    """What a `pnpm-workspace.yaml` ignores and takes under the package age."""

    ignores: list[str]
    excludes: list[str]


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _documents(text: str) -> list[Any] | None:
    if len(text.encode("utf-8")) > YAML_BYTES:
        return None
    try:
        return list(yaml.safe_load_all(text))
    except yaml.YAMLError, RecursionError:
        return None


def _workspace(text: str) -> Workspace | None:
    documents = _documents(text)
    if documents is None:
        return None
    ignores: list[str] = []
    excludes: list[str] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        audit_config = document.get("auditConfig")
        audit = document.get("audit")
        ignores += (
            _strings(audit_config.get("ignoreGhsas")) if isinstance(audit_config, dict) else []
        )
        ignores += _strings(audit.get("ignore")) if isinstance(audit, dict) else []
        excludes += _strings(document.get("minimumReleaseAgeExclude"))
    return Workspace(ignores, excludes)


def _packages(text: str) -> frozenset[str] | None:
    documents = _documents(text)
    if documents is None:
        return None
    keys: Iterable[str] = (
        str(key)
        for document in documents
        if isinstance(document, dict) and isinstance(document.get("packages"), dict)
        for key in document["packages"]
    )
    return frozenset(keys)


async def in_thread[T](function: Callable[..., T], *args: object) -> T | None:
    """`function(*args)` in a worker thread; None when it takes longer than `TIMEOUT_S`."""
    loop = asyncio.get_running_loop()
    if loop not in _limiters:
        _limiters[loop] = anyio.CapacityLimiter(LIMITER_SLOTS)
    try:
        async with asyncio.timeout(TIMEOUT_S):
            return await to_thread.run_sync(
                function, *args, limiter=_limiters[loop], abandon_on_cancel=True
            )
    except TimeoutError:
        return None


async def workspace_lists(text: str) -> Workspace | None:
    """The ignores and age exclusions of a `pnpm-workspace.yaml`; None when it does not read."""
    return await in_thread(_workspace, text)


async def lock_packages(text: str) -> frozenset[str] | None:
    """The `packages` keys (`<name>@<version>`) of every document of a `pnpm-lock.yaml`."""
    return await in_thread(_packages, text)
