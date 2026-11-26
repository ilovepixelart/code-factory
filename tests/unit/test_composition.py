"""The composition root wires each port to the module that owns its facts, and nothing replaces it.

`Services.add` replaces an earlier registration, so a module listed late that registers a class an
earlier module registered silently takes its place.
"""

import pytest

from code_factory.app import MODULES, build_resources, build_services
from code_factory.platform.config import Settings
from code_factory.platform.served import Served
from code_factory.platform.services import Services
from code_factory.team.service import (
    AgentSource,
    GateSource,
    JobSource,
    OwnerSource,
    RunSource,
    SessionSource,
    TicketSource,
)

TEAM_PORTS = (
    AgentSource,
    RunSource,
    GateSource,
    TicketSource,
    OwnerSource,
    SessionSource,
    JobSource,
)


def test_each_team_port_resolves_to_the_module_that_owns_its_facts(
    offline_settings: Settings,
) -> None:
    services = build_services(build_resources(offline_settings, database=False))
    owners = {key.__name__: type(services.get(key)).__module__ for key in TEAM_PORTS}
    assert owners == {
        "AgentSource": "code_factory.agents.module",
        "RunSource": "code_factory.runs.service.neighbours",
        "GateSource": "code_factory.checks.module",
        "TicketSource": "code_factory.board.adapters",
        "OwnerSource": "code_factory.board.adapters",
        "SessionSource": "code_factory.sessions.module",
        "JobSource": "code_factory.board.adapters",
    }


def test_no_module_registers_a_class_an_earlier_module_registered(
    offline_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    added: list[tuple[str, str]] = []
    module_name = "app"
    real_add = Services.add

    def recording[T](self: Services, key: type[T], service: T) -> None:
        added.append((key.__name__, module_name))
        real_add(self, key, service)

    monkeypatch.setattr(Services, "add", recording)
    resources = build_resources(offline_settings, database=False)
    services = Services()
    services.add(Served, Served.none())
    for module in MODULES:
        module_name = module.name
        if module.provide is not None:
            module.provide(services, resources)
    first: dict[str, str] = {}
    twice = []
    for key, by in added:
        if key in first:
            twice.append((key, first[key], by))
        first.setdefault(key, by)
    assert twice == []
