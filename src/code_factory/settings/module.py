"""The `settings` module as the platform sees it."""

from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.settings import tables  # noqa: F401  # puts intake_key_grants on the metadata
from code_factory.settings.cli import config_command, docs_command, intake_key_command
from code_factory.settings.service import SettingsService


def _provide(services: Services, resources: Resources) -> None:
    services.add(SettingsService, SettingsService(resources.uow))


module = Module(
    name="settings",
    provide=_provide,
    commands=(config_command, docs_command, intake_key_command),
)
