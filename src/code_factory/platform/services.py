"""The services of one running process, keyed by their class.

`code_factory.app` registers each module's service; routes and tools look it up by class, so the
platform stays ignorant of which modules exist.
"""

from typing import cast


class Services:
    """A registry with one service per class."""

    def __init__(self) -> None:
        self._items: dict[type, object] = {}

    def add[T](self, key: type[T], service: T) -> None:
        """Register `service` under `key`, replacing an earlier one."""
        self._items[key] = service

    def get[T](self, key: type[T]) -> T:
        """The service registered under `key`; a module lists after the modules it depends on."""
        try:
            return cast("T", self._items[key])  # add() pairs every key with its instance
        except KeyError:
            msg = f"no service is registered for {key.__name__}; list its module in app.MODULES"
            raise LookupError(msg) from None
