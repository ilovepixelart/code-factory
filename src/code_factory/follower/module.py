"""The `follower` module as the platform sees it."""

import os

from code_factory.board.service import CardQueue
from code_factory.follower import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.follower.cli import follower_command
from code_factory.follower.ports import FollowerPorts
from code_factory.follower.service import FollowerService, Leader, QueueService
from code_factory.follower.service.neighbours import (
    BoardAdapter,
    FilingAdapter,
    QueueAdapter,
    WorkAdapter,
)
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services

PASS_S = float(os.environ.get("CODE_FACTORY_FOLLOWER_SECONDS", "5"))


def _provide(services: Services, resources: Resources) -> None:
    queue = QueueService(resources.uow)
    ports = FollowerPorts(
        board=BoardAdapter(services), work=WorkAdapter(services), filing=FilingAdapter(services)
    )
    services.add(QueueService, queue)
    services.add(CardQueue, QueueAdapter(services, queue))
    services.add(FollowerService, FollowerService(resources.uow, ports, queue))
    leader = Leader(resources.engine)
    services.add(Leader, leader)
    resources.on_stop.append(leader.let_go)


def _background(services: Services, tasks: BackgroundTasks) -> None:
    follower, leader = services.get(FollowerService), services.get(Leader)
    tasks.start("follower", lambda: follower.run(PASS_S, leader.lead))


module = Module(
    name="follower", provide=_provide, commands=(follower_command,), background=_background
)
