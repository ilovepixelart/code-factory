"""`code-factory sessions [list|ingest|rebuild]`: the ledger from the command line."""

import argparse
import sys

from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.platform.text import Style, render
from code_factory.sessions.service import SessionService

ACTIONS = {
    "list": "print every session as JSON (the default)",
    "ingest": "take the spool into the ledger and say how many lines",
    "rebuild": "derive every session's view again from its events",
}


def _configure(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action")
    for name, help_text in ACTIONS.items():
        actions.add_parser(name, help=help_text)


async def _run(args: argparse.Namespace, services: Services) -> int:
    sessions = services.get(SessionService)
    match args.action or "list":
        case "ingest":
            taken = await sessions.ingest_once(wait=True)
            sys.stdout.write(f"{taken.lines} lines, {taken.rejects} rejects\n")
        case "rebuild":
            sys.stdout.write(f"{await sessions.rebuild_views()}\n")
        case _:
            await sessions.ingest_once(wait=True)
            answer = await sessions.list_sessions(None)
            sys.stdout.write(render(answer, Style.INDENT2) + "\n")
    return 0


sessions_command = Command(
    "sessions",
    "list agent sessions, or take the capture spool into the ledger",
    configure=_configure,
    run_async=_run,
)
