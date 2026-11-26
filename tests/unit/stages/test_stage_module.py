"""The module as the app wires it: its service, its command, the observer task and its period."""

import pytest

from code_factory.app import MODULES, build_resources, build_services
from code_factory.platform.background import background_tasks
from code_factory.platform.config import Settings
from code_factory.platform.errors import SettingsError
from code_factory.stages.module import module, observe_period
from code_factory.stages.service import StageService


def test_the_module_is_listed_after_the_modules_it_reads() -> None:
    names = [m.name for m in MODULES]

    assert names.index("stages") > max(
        names.index(n) for n in ("tickets", "releases", "repositories", "settings")
    )


def test_the_module_provides_the_stage_service_and_the_stage_command(
    offline_settings: Settings,
) -> None:
    services = build_services(build_resources(offline_settings, database=False))

    assert isinstance(services.get(StageService), StageService)
    assert [c.name for c in module.commands] == ["stage"]


@pytest.mark.parametrize(
    ("given", "seconds"),
    [(None, 30.0), ("", 30.0), ("  ", 30.0), ("60", 60.0), ("5", 5.0), ("4", 5.0), ("0.5", 5.0)],
)
def test_the_observer_period_defaults_to_thirty_seconds_and_is_never_under_five(
    given: str | None, seconds: float
) -> None:
    environment = {} if given is None else {"CODE_FACTORY_STAGE_OBSERVE_SECONDS": given}

    assert observe_period(environment) == seconds


def test_a_period_that_is_no_number_says_what_to_write() -> None:
    with pytest.raises(SettingsError, match="write the seconds between observations"):
        observe_period({"CODE_FACTORY_STAGE_OBSERVE_SECONDS": "soon"})


@pytest.mark.parametrize("given", ["inf", "-inf", "nan"])
def test_a_period_that_is_not_finite_says_what_to_write(given: str) -> None:
    with pytest.raises(SettingsError, match="write the seconds between observations"):
        observe_period({"CODE_FACTORY_STAGE_OBSERVE_SECONDS": given})


async def test_the_background_hook_starts_the_observer_task(offline_settings: Settings) -> None:
    services = build_services(build_resources(offline_settings, database=False))
    assert module.background is not None

    async with background_tasks() as tasks:
        module.background(services, tasks)

        assert "stage-observer" in tasks.names
