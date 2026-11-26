"""The `push` module as the platform sees it.

List it after inbox, runs and talk: it reads the Inbox and answers through their services.
"""

import os
from datetime import UTC, datetime

from code_factory.inbox.service import InboxService
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.module import Module, Resources
from code_factory.platform.served import Served
from code_factory.platform.services import Services
from code_factory.push import tables  # noqa: F401  # puts the push tables on the metadata
from code_factory.push.adapters import HttpDelivery
from code_factory.push.cli import push_command
from code_factory.push.routes import router
from code_factory.push.service import PushService
from code_factory.runs.service import PermissionService
from code_factory.talk.service import TalkService

PASS_S = float(os.environ.get("CODE_FACTORY_PUSH_SECONDS", "5"))


def _provide(services: Services, resources: Resources) -> None:
    inbox = services.get(InboxService)
    push = PushService(
        resources.uow,
        inbox,
        services.get(PermissionService),
        services.get(TalkService),
        HttpDelivery(),
        lambda: datetime.now(UTC),
    )
    services.add(PushService, push)
    inbox.report_push(push)


def _background(services: Services, tasks: BackgroundTasks) -> None:
    push, served = services.get(PushService), services.get(Served)
    tasks.start("push", lambda: push.run(PASS_S, lambda: served.base_url))


module = Module(
    name="push",
    provide=_provide,
    router=router,
    commands=(push_command,),
    background=_background,
)
