"""The `undo` module as the platform sees it."""

from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.undo import tables  # noqa: F401  # puts undo_entries on the metadata
from code_factory.undo.cli import undo_command
from code_factory.undo.routes import router
from code_factory.undo.service import UndoService


def _provide(services: Services, resources: Resources) -> None:
    services.add(UndoService, UndoService(resources.uow))


module = Module(name="undo", provide=_provide, router=router, commands=(undo_command,))
