"""The `agents` module as the platform sees it."""

from code_factory.agents import tables  # noqa: F401  # puts its tables on Base.metadata
from code_factory.agents.cli import agents_command, connections_command, secret_command
from code_factory.agents.routes import router
from code_factory.agents.service import AgentService
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.team.models import TeamAgent
from code_factory.team.service import AgentSource


class _TeamAgents:
    """The team's view of the agents: its `TeamAgent` from each agent's facts."""

    def __init__(self, agents: AgentService) -> None:
        self._agents = agents

    async def team_agents(self) -> list[TeamAgent]:
        """Every defined agent in roster order; `refusal` is the failed model check sentence."""
        return [TeamAgent(**facts.model_dump()) for facts in await self._agents.team_agents()]


def _provide(services: Services, resources: Resources) -> None:
    agents = AgentService(resources.uow)
    services.add(AgentService, agents)
    services.add(AgentSource, _TeamAgents(agents))


module = Module(
    name="agents",
    provide=_provide,
    commands=(agents_command, connections_command, secret_command),
    router=router,
)
