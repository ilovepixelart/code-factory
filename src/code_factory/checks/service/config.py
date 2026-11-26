"""What a repository's configuration says of one run."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from code_factory.checks.adapters import ContainerSpec, Setup
from code_factory.checks.models import Containment, Scope
from code_factory.platform.errors import BadRequestError

if TYPE_CHECKING:  # the models module is not a layer another module may import at run time
    from code_factory.settings.models.config import RepositoryConfig

DEFAULT_SETUP_LIMIT_S = 600
CONFIG_FILE = ".code-factory/config.toml"
_MISSING = {
    Scope.REACHED: f"no checks command in {CONFIG_FILE}",
    Scope.FAST: f"no [checks] fast command in {CONFIG_FILE}",
    Scope.FULL: f"no [checks] main command in {CONFIG_FILE}",
}


@dataclass(frozen=True)
class RunConfig:
    """The settings one run reads, with the defaults the checks module owns."""

    commands: dict[Scope, str | None]
    timeout: int | None
    spec: ContainerSpec
    containerised: bool
    slots: int
    sandboxed: bool
    setup: Setup | None
    verify: str | None
    watch_days: int | None

    def command(self, scope: Scope) -> str:
        """The command of `scope`; `BadRequestError` names the key that is missing."""
        found = self.commands[scope]
        if found is None:
            raise BadRequestError(_MISSING[scope])
        return found

    def containment(self) -> Containment:
        """How a checks run is kept from the machine."""
        if not self.sandboxed:
            return Containment.NONE
        return Containment.CONTAINER if self.containerised else Containment.SRT


def run_config(config: RepositoryConfig) -> RunConfig:
    """`config` read for a run."""
    checks, agents, release = config.checks, config.agents, config.release
    spec = ContainerSpec(
        engine=checks.container_engine if checks else None,
        image=checks.container if checks else None,
        file=checks.container_file if checks else None,
        mounts=tuple(checks.container_mounts or ()) if checks else (),
    )
    setup = None
    if agents is not None and agents.setup is not None:
        limit = agents.setup_timeout if agents.setup_timeout is not None else DEFAULT_SETUP_LIMIT_S
        setup = Setup(command=agents.setup, limit_s=float(limit))
    return RunConfig(
        commands={
            Scope.REACHED: checks.command if checks else None,
            Scope.FAST: checks.fast if checks else None,
            Scope.FULL: checks.main if checks else None,
        },
        timeout=checks.timeout if checks else None,
        spec=spec,
        containerised=spec.image is not None or spec.file is not None,
        slots=checks.container_slots if checks and checks.container_slots is not None else 1,
        sandboxed=agents is None or agents.sandbox is not False,
        setup=setup,
        verify=release.verify if release else None,
        watch_days=release.watch_days if release else None,
    )
