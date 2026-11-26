"""The team module's public API.

Other modules reach the team through `TeamService` and register themselves as the ports in
`code_factory.team.service.ports` (`AgentSource`, `RunSource`, `TicketSource`, `GateSource`,
`OwnerSource`, `SessionSource`, `JobSource`).
"""

from code_factory.team.service.ports import (
    AgentSource,
    GateSource,
    JobSource,
    OwnerSource,
    RunSource,
    SessionSource,
    TeamPorts,
    TicketSource,
)
from code_factory.team.service.team import TeamService

__all__ = [
    "AgentSource",
    "GateSource",
    "JobSource",
    "OwnerSource",
    "RunSource",
    "SessionSource",
    "TeamPorts",
    "TeamService",
    "TicketSource",
]
