"""The `hooks` module as the platform sees it."""

from code_factory.hooks.adapters.opener import BrowserOpener
from code_factory.hooks.adapters.probe import BoardProbe
from code_factory.hooks.cli import commands
from code_factory.hooks.ports import BoardAddress, Checkouts, HookPorts
from code_factory.hooks.routes import router
from code_factory.hooks.service import HookService
from code_factory.hooks.service.neighbours import (
    AuthAdapter,
    CheckoutsAdapter,
    MemoryAdapter,
    PermissionsAdapter,
    ReleasesAdapter,
    RepositoriesAdapter,
    RunsAdapter,
    TalkAdapter,
    TicketsAdapter,
)
from code_factory.platform.module import Module, Resources
from code_factory.platform.served import Served
from code_factory.platform.services import Services
from code_factory.runs.models import RunHooks

DEFAULT_PORT = 4000


def _provide(services: Services, resources: Resources) -> None:
    served = services.get(Served)
    checkouts = CheckoutsAdapter(services)
    ports = HookPorts(
        talk=TalkAdapter(services),
        permissions=PermissionsAdapter(services),
        runs=RunsAdapter(services),
        tickets=TicketsAdapter(services),
        memory=MemoryAdapter(services),
        checkouts=checkouts,
        auth=AuthAdapter(services),
        releases=ReleasesAdapter(services),
        repositories=RepositoriesAdapter(services),
        opener=BrowserOpener(),
        probe=BoardProbe(),
        board=BoardAddress(
            host=served.address or "127.0.0.1",
            port=served.port or resources.settings.port or DEFAULT_PORT,
        ),
    )
    services.add(HookService, HookService(ports))
    services.add(Checkouts, checkouts)


module = Module(name="hooks", provide=_provide, commands=commands, router=router)


class RunHookCommands:
    """The runs module's hook source: the commands of the hooks a run's settings carry.

    Read when a run starts, after every module is provided.
    """

    def __init__(self, services: Services) -> None:
        self._services = services

    def run_hooks(self) -> RunHooks:
        """How the permission, tell, recall and rewrite hooks start."""
        made = self._services.get(HookService).hook_commands()
        return RunHooks(
            permission=made.permission, tell=made.tell, recall=made.recall, rewrite=made.rewrite
        )
