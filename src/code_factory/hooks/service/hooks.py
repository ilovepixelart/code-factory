"""`HookService`: every use case of the hooks module, assembled from its parts."""

from code_factory.hooks.models import HookCommands
from code_factory.hooks.service.commands import build_commands
from code_factory.hooks.service.owner import OwnerMixin
from code_factory.hooks.service.permission import PermissionMixin
from code_factory.hooks.service.recall import RecallMixin
from code_factory.hooks.service.reports import ReportMixin
from code_factory.hooks.service.tell import TellMixin


class HookService(TellMixin, PermissionMixin, RecallMixin, OwnerMixin, ReportMixin):
    """What the agent hooks and the owner's small commands ask of the board."""

    def hook_commands(self) -> HookCommands:
        """The command strings that start each hook.

        One definition of how a hook starts, for the agents module's settings and `install`.
        """
        if self._commands is None:
            self._commands = build_commands()
        return self._commands
