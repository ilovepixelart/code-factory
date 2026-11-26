"""`code-factory undo sweep`: delete the expired undo entries once."""

import argparse
import sys

from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.undo.service import UndoService


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["sweep"])


async def _run(_args: argparse.Namespace, services: Services) -> int:
    removed = await services.get(UndoService).sweep()
    sys.stdout.write(f"removed {removed} expired undo entries\n")
    return 0


undo_command = Command(
    "undo", "delete the expired undo entries", configure=_configure, run_async=_run
)
