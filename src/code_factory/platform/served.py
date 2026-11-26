"""What this process serves: the address, the port, the link that names it, and its stop signal.

Registered in `Services` by `app.build_services`, so the Host guard, the canonical-host redirect and
the sign-in link read one value. A process that does not serve (tests, the stdio MCP server, a
command) has `Served.none()`.
"""

import asyncio
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Served:
    """The listener of a served board.

    `port` is the real one (a request for port 0 is the one the system chose). `both_loopbacks` is
    whether `127.0.0.1` and `[::1]` are both held, so `localhost` names this board and no other
    program. `stopping` is set before the connections close, so a long-lived stream can end first.
    """

    address: str
    port: int
    both_loopbacks: bool
    base_url: str
    stopping: asyncio.Event = field(default_factory=asyncio.Event, compare=False, repr=False)

    @classmethod
    def none(cls) -> Served:
        """The value of a process that serves nothing."""
        return cls(address="", port=0, both_loopbacks=False, base_url="")

    @property
    def serving(self) -> bool:
        """Whether a link to this process exists."""
        return bool(self.base_url)
