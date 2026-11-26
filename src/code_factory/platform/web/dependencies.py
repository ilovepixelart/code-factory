"""Dependencies, declared once as `Annotated` aliases and used in route signatures.

There is no session dependency: a route calls a service and the service opens its own unit of
work (`code_factory.platform.db.UnitOfWork`), so the commit happens before the response is sent.
"""

from collections.abc import Callable
from typing import Annotated, cast

from fastapi import Depends, Request

from code_factory.platform.config import Settings
from code_factory.platform.services import Services


def get_settings(request: Request) -> Settings:
    """The settings the app was created with."""
    return cast("Settings", request.app.state.settings)


def service_of[T](key: type[T]) -> Callable[[Request], T]:
    """A dependency answering with the service registered under `key`.

    A module declares `Annotated[MyService, Depends(service_of(MyService))]` once in its routes.
    """

    def dependency(request: Request) -> T:
        return cast("Services", request.app.state.services).get(key)

    return dependency


SettingsDep = Annotated[Settings, Depends(get_settings)]
