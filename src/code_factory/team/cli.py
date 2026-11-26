"""`code-factory team leases|release`: the claims on tickets, and freeing a stuck one."""

import argparse
import sys
from datetime import UTC, datetime

from code_factory.platform.errors import BadRequestError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.team.rules import who
from code_factory.team.service import TeamService


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["leases", "release"])
    parser.add_argument("ticket", nargs="?", help="release: the ticket whose claim to free, CF-n")


def _when(seconds: float) -> str:
    return f"{datetime.fromtimestamp(seconds, UTC):%Y-%m-%d %H:%M:%S}"


async def _run(args: argparse.Namespace, services: Services) -> int:
    team = services.get(TeamService)
    if args.action == "release":
        if not args.ticket:
            raise BadRequestError(
                "release needs a ticket: `code-factory team leases` lists the claims"
            )
        await team.force_release(args.ticket)
        sys.stdout.write(f"released the claim on {args.ticket}\n")
        return 0
    sys.stdout.write("TICKET  HOLDER  RUNS  CLAIMED  BEAT  HOLDS\n")
    for view in await team.list_claims():
        sys.stdout.write(
            f"{view.ticket_id}  {who(view.agent)}  {','.join(view.runs) or '-'}  "
            f"{_when(view.claimed_at)}  {_when(view.beat_at)}  {'yes' if view.holds else 'no'}\n"
        )
    return 0


team_command = Command(
    "team",
    "list the claims on tickets, or free a stuck one",
    configure=_configure,
    run_async=_run,
)
