"""The `auth` module as the platform sees it."""

from code_factory.auth import tables  # noqa: F401  # puts auth_tokens on the metadata
from code_factory.auth.cli import command, open_server, token_command
from code_factory.auth.routes import router
from code_factory.auth.service import AuthService, sweep_forever
from code_factory.platform.background import BackgroundTasks
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services

SWEEP_INTERVAL_S = 3600.0


def _provide(services: Services, resources: Resources) -> None:
    services.add(AuthService, AuthService(resources.uow))


def _background(services: Services, tasks: BackgroundTasks) -> None:
    auth = services.get(AuthService)
    tasks.start("auth-sweep", lambda: sweep_forever(auth, interval_s=SWEEP_INTERVAL_S))


module = Module(
    name="auth",
    provide=_provide,
    router=router,
    commands=(command, open_server, token_command),
    background=_background,
)
