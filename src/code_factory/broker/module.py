"""The `broker` module as the platform sees it."""

from code_factory.agents.service import AgentService
from code_factory.broker import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.broker.cli import broker_command
from code_factory.broker.service import BrokerService
from code_factory.broker.service.neighbours import AgentConnections, SessionUsage
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.sessions.service import SessionService


def _provide(services: Services, resources: Resources) -> None:
    service = BrokerService(
        resources.uow,
        resources.settings,
        AgentConnections(services.get(AgentService)),
        SessionUsage(services.get(SessionService)),
    )
    services.add(BrokerService, service)
    resources.on_stopping.append(service.shutdown)


def _background(services: Services, tasks: BackgroundTasks) -> None:
    service = services.get(BrokerService)
    tasks.start("broker-listener", lambda: service.serve(service.stopping))
    tasks.start("broker-sweep", lambda: service.sweep_loop(service.stopping))


module = Module(name="broker", provide=_provide, background=_background, commands=(broker_command,))
