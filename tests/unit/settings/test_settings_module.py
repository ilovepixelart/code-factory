"""The settings module as the composition root builds it."""

from code_factory.app import MODULES, build_resources, build_services
from code_factory.platform.config import Settings
from code_factory.settings.service import SettingsService


def test_the_composition_root_provides_the_settings_service(offline_settings: Settings) -> None:
    services = build_services(build_resources(offline_settings))
    assert isinstance(services.get(SettingsService), SettingsService)


def test_the_settings_module_adds_its_three_commands() -> None:
    (module,) = (m for m in MODULES if m.name == "settings")
    assert [c.name for c in module.commands] == ["config", "docs", "intake-key"]
