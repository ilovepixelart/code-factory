"""The module as the app wires it: its service, its place in the order and its undo handler."""

from code_factory.app import MODULES, build_resources, build_services
from code_factory.platform.config import Settings
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.undo.service import UndoService


def test_the_module_is_listed_after_the_modules_it_calls() -> None:
    names = [m.name for m in MODULES]

    assert names.index("ticket_writes") > max(
        names.index(n) for n in ("tickets", "git", "repositories", "stages", "undo")
    )


def test_the_module_provides_the_write_service_and_registers_its_revert_handler(
    offline_settings: Settings,
) -> None:
    services = build_services(build_resources(offline_settings, database=False))

    assert isinstance(services.get(TicketWriteService), TicketWriteService)
    undo = services.get(UndoService)
    assert "tickets.revert" in undo._handlers  # the registry is the only witness
