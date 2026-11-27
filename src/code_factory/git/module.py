"""The `git` module as the platform sees it."""

from collections.abc import Callable

from code_factory.git import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.git.adapters.runner import GitRunner
from code_factory.git.cli import COMMANDS
from code_factory.git.service import GitPorts, GitService
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services


def build_module(ports_of: Callable[[Services], GitPorts]) -> Module:
    """The module over the ports `ports_of` builds from the registry (`code_factory.app`)."""

    def provide(services: Services, resources: Resources) -> None:
        service = GitService(resources.uow, GitRunner(()), ports_of(services))
        services.add(GitService, service)

    def background(services: Services, tasks: BackgroundTasks) -> None:
        # The platform has no readiness hook for a module: a git too old for the merge checks is
        # logged once, with its sentence, when the application starts.
        tasks.start("git-probe", services.get(GitService).probe)

    return Module(name="git", provide=provide, commands=COMMANDS, background=background)
