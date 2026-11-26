"""Pure rules over a Claude Code settings object: add and remove the board's hooks."""

import copy
import shlex
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any

from code_factory.commands.models import HookEntry
from code_factory.platform.errors import BadRequestError

NOT_AN_OBJECT = "the settings file holds no JSON object"
HOOKS_NOT_AN_OBJECT = '"hooks" in the settings file is not an object'


def _script(command: str) -> tuple[str, ...] | None:
    """The board script a command runs and its arguments: (file name, *args), or None."""
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    for index, word in enumerate(words):
        path = PurePosixPath(word)
        if path.suffix == ".py" and "code_factory" in path.parts:
            return (path.name, *words[index + 1 :])
    if words and PurePosixPath(words[0]).name == "code-factory":
        return ("code-factory", *words[1:])
    return None


def owns(existing: str, wanted: str) -> bool:
    """Whether an installed command is this hook: the same board script and arguments.

    The interpreter or install folder may have moved; another tool's script never matches.
    """
    if existing == wanted:
        return True
    mine = _script(wanted)
    return mine is not None and _script(existing) == mine


def _hooks(settings: dict[str, Any]) -> dict[str, Any]:
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise BadRequestError(HOOKS_NOT_AN_OBJECT)
    return hooks


def _event_list(hooks: dict[str, Any], event: str) -> list[Any]:
    items = hooks.setdefault(event, [])
    if not isinstance(items, list):
        msg = f'"hooks.{event}" in the settings file is not a list'
        raise BadRequestError(msg)
    return items


def _hook(entry: HookEntry) -> dict[str, Any]:
    hook: dict[str, Any] = {"type": "command", "command": entry.command}
    if entry.timeout is not None:
        hook["timeout"] = entry.timeout
    if entry.asynchronous:
        hook["async"] = True
    return hook


def _widen(item: dict[str, Any], hook: dict[str, Any], entry: HookEntry) -> bool:
    changed = False
    if entry.matcher and item.get("matcher", "") != entry.matcher:
        item["matcher"] = entry.matcher
        changed = True
    for key in ("timeout", "async"):
        wanted = _hook(entry).get(key)
        if hook.get(key) != wanted:
            if wanted is None:
                hook.pop(key, None)
            else:
                hook[key] = wanted
            changed = True
    if hook.get("command") != entry.command:
        hook["command"] = entry.command
        changed = True
    return changed


def _present(items: list[Any], entry: HookEntry) -> tuple[dict[str, Any], dict[str, Any]] | None:
    for item in items:
        for hook in item.get("hooks", []) if isinstance(item, dict) else []:
            if isinstance(hook, dict) and owns(str(hook.get("command", "")), entry.command):
                return item, hook
    return None


def add_hooks(settings: object, entries: Sequence[HookEntry]) -> dict[str, Any] | None:
    """The settings with every entry installed, or `None` when nothing changes."""
    if not isinstance(settings, dict):
        raise BadRequestError(NOT_AN_OBJECT)
    result = copy.deepcopy(settings)
    hooks = _hooks(result)
    changed = False
    for entry in entries:
        items = _event_list(hooks, entry.event)
        found = _present(items, entry)
        if found is not None:
            changed = _widen(*found, entry) or changed
            continue
        item: dict[str, Any] = {"hooks": [_hook(entry)]}
        if entry.matcher:
            item["matcher"] = entry.matcher
        items.append(item)
        changed = True
    return result if changed else None


def _ours(hook: object, entries: Sequence[HookEntry]) -> bool:
    if not isinstance(hook, dict):
        return False
    return any(owns(str(hook.get("command", "")), e.command) for e in entries)


def remove_hooks(settings: object, entries: Sequence[HookEntry]) -> dict[str, Any] | None:
    """The settings without the board's hooks, or `None` when none was there."""
    if not isinstance(settings, dict):
        raise BadRequestError(NOT_AN_OBJECT)
    result = copy.deepcopy(settings)
    hooks = result.get("hooks")
    if not isinstance(hooks, dict):
        return None
    changed = False
    for event in list(hooks):
        items = hooks[event]
        if not isinstance(items, list):
            continue
        kept = []
        for item in items:
            inner = item.get("hooks", []) if isinstance(item, dict) else []
            left = [h for h in inner if not _ours(h, entries)]
            changed = changed or len(left) != len(inner)
            if left or not inner:
                kept.append({**item, "hooks": left} if inner else item)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        del result["hooks"]
    return result if changed else None
