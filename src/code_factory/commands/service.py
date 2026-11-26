"""The commands' use cases: install and uninstall the hooks, track and untrack repositories."""

from collections.abc import Callable
from pathlib import Path

from code_factory.commands.adapters import SettingsFile, folder_problem, settings_path
from code_factory.commands.models import HookChange, HookEntry, Scope
from code_factory.commands.rules import add_hooks, remove_hooks
from code_factory.platform.errors import BadRequestError
from code_factory.repositories.models import RepositoryRecord
from code_factory.repositories.service import RepositoryService
from code_factory.settings.service import SettingsService

RECALL_MATCHER = "startup|resume|clear|compact"
GUARD_TIMEOUT_S = 30


def hook_entries(capture: str, events: tuple[str, ...], recall: str, guard: str) -> list[HookEntry]:
    """The capture hook on every event, the recall at session start, the rewrite guard on Bash."""
    entries = [HookEntry(event=e, command=capture, asynchronous=True) for e in events]
    entries.append(HookEntry(event="SessionStart", command=recall, matcher=RECALL_MATCHER))
    entries.append(
        HookEntry(event="PreToolUse", command=guard, matcher="Bash", timeout=GUARD_TIMEOUT_S)
    )
    return entries


class CommandService:
    """Hooks in a Claude Code settings file."""

    def __init__(self, entries: Callable[[], list[HookEntry]]) -> None:
        self._entries = entries

    async def install(self, scope: Scope, project: Path) -> HookChange:
        """Write the board's hooks, keeping everything else; nothing written when already there."""
        file = SettingsFile(settings_path(scope, project))
        wanted = add_hooks(await file.load(), self._entries())
        if wanted is None:
            return HookChange(path=file.path, changed=False)
        return HookChange(path=file.path, changed=True, backup=await file.replace(wanted))

    async def uninstall(self, scope: Scope, project: Path) -> HookChange:
        """Remove only the board's hooks."""
        file = SettingsFile(settings_path(scope, project))
        left = remove_hooks(await file.load(), self._entries())
        if left is None:
            return HookChange(path=file.path, changed=False)
        return HookChange(path=file.path, changed=True, backup=await file.replace(left))


class RepositoryTracker:
    """Tracking a repository from a folder the owner names: checked on disk and in git first."""

    def __init__(self, repositories: RepositoryService, settings: SettingsService) -> None:
        self._repositories = repositories
        self._settings = settings

    async def track(self, given: str) -> RepositoryRecord:
        """Track the main checkout of the repository holding `given`.

        `BadRequestError` with a sentence for a relative path, a missing one, a file, and a folder
        in no git repository.
        """
        path = Path(given)
        if not path.is_absolute():
            msg = f"{given} is not an absolute path"
            raise BadRequestError(msg)
        problem = await folder_problem(path)
        if problem is not None:
            msg = f"{given} {problem}: give the folder of a git repository"
            raise BadRequestError(msg)
        checkout = await self._settings.checkout_of(path)
        if checkout is None:
            msg = (
                f"{given} is not a git repository: run git init there, "
                "or give the repository's folder"
            )
            raise BadRequestError(msg)
        return await self._repositories.track(checkout)
