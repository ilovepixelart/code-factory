"""The `commands` module as the platform sees it."""

from code_factory.commands.cli import commands
from code_factory.commands.models import HookEntry
from code_factory.commands.routes import router
from code_factory.commands.service import CommandService, RepositoryTracker, hook_entries
from code_factory.hooks.service import HookService
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from code_factory.sessions.service import SessionService
from code_factory.settings.service import SettingsService


def _provide(services: Services, resources: Resources) -> None:  # noqa: ARG001
    def entries() -> list[HookEntry]:
        capture = services.get(SessionService).capture_hook()
        hooks = services.get(HookService).hook_commands()
        return hook_entries(capture.command, capture.events, hooks.recall_cli, hooks.rewrite)

    services.add(CommandService, CommandService(entries))
    services.add(
        RepositoryTracker,
        RepositoryTracker(services.get(RepositoryService), services.get(SettingsService)),
    )


module = Module(name="commands", provide=_provide, router=router, commands=commands)
