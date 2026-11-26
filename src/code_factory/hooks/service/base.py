"""What the hooks service's parts share: the ports, the clock and the waits."""

import logging
from collections.abc import Callable
from datetime import datetime

from code_factory.hooks.models import HookCommands
from code_factory.hooks.ports import HookPorts
from code_factory.tickets.service import utc_now

logger = logging.getLogger(__name__)

WAIT_S = 540.0  # the owner's wait; the hook is installed with a 600 s timeout
POLL_S = 0.25  # how often a waiting request asks whether its hook is still there
CLEANUP_S = 2.0  # what a cancelled request is given to withdraw itself


class Collaborators:
    """The parts of `HookService` read these."""

    def __init__(
        self,
        ports: HookPorts,
        *,
        clock: Callable[[], datetime] = utc_now,
        wait_s: float = WAIT_S,
        poll_s: float = POLL_S,
        commands: HookCommands | None = None,
    ) -> None:
        self._ports = ports
        self._clock = clock
        self._wait_s = wait_s
        self._poll_s = poll_s
        self._commands = commands
