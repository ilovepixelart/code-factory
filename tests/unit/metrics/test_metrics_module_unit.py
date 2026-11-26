"""The module's adapters against the real services, its command line and its registration."""

import pytest

from code_factory.app import MODULES, build_resources, build_services
from code_factory.metrics.service import MetricsService
from code_factory.platform.config import Settings
from code_factory.platform.services import Services


def test_the_module_is_registered_after_the_modules_it_reads() -> None:
    names = [m.name for m in MODULES]
    assert names.index("metrics") > max(names.index(n) for n in ("repositories", "tickets", "git"))
    [module] = [m for m in MODULES if m.name == "metrics"]
    assert module.background is not None
    assert [c.name for c in module.commands] == ["metrics"]


@pytest.fixture
def services(metrics: MetricsService) -> Services:
    registry = Services()
    registry.add(MetricsService, metrics)
    return registry


def test_the_real_modules_build_a_metrics_service(offline_settings: Settings) -> None:
    services = build_services(build_resources(offline_settings, database=False))
    assert isinstance(services.get(MetricsService), MetricsService)
