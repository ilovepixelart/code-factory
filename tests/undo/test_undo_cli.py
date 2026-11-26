"""`code-factory undo sweep` and the module's registration."""

import argparse
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from code_factory.app import MODULES
from code_factory.platform.db import UnitOfWork
from code_factory.platform.module import Resources
from code_factory.platform.services import Services
from code_factory.undo.cli import undo_command
from code_factory.undo.module import module
from code_factory.undo.service import UndoService

START = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


async def _noop(_payload: dict[str, Any], _by: str) -> None:
    return None


async def test_sweep_prints_how_many_expired_entries_it_removed(
    uow: UnitOfWork, capsys: pytest.CaptureFixture[str]
) -> None:
    offered = UndoService(uow, clock=lambda: START)
    offered.register("test.revert", _noop)
    await offered.offer("test.revert", {}, "one")
    await offered.offer("test.revert", {}, "two")
    later = UndoService(uow, clock=lambda: START + timedelta(minutes=5))
    services = Services()
    services.add(UndoService, later)
    parser = argparse.ArgumentParser(prog="undo")
    undo_command.configure(parser)
    run_async = undo_command.run_async
    assert run_async is not None
    code = await run_async(parser.parse_args(["sweep"]), services)
    assert (code, capsys.readouterr().out) == (0, "removed 2 expired undo entries\n")


def test_the_module_provides_an_undo_service_on_the_units_of_work(uow: UnitOfWork) -> None:
    services = Services()
    resources = Resources(settings=None, engine=None, uow=uow, tasks=None)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]  # provide reads only the unit of work
    assert module.provide is not None
    module.provide(services, resources)
    assert isinstance(services.get(UndoService), UndoService)
    assert module in MODULES
