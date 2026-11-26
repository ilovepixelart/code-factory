"""`code-factory broker [status|sweep]`: the broker's tokens and keys from the command line."""

import argparse
import sys

from code_factory.broker.models import TokenInfo
from code_factory.broker.service import BrokerService
from code_factory.platform.module import Command
from code_factory.platform.services import Services

ACTIONS = {
    "status": "list the live tokens and the keys waiting to be deleted (the default)",
    "sweep": "run one sweep pass here, deleting the keys of runs that ended",
}
FAILED = 1


def _configure(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action")
    for name, help_text in ACTIONS.items():
        actions.add_parser(name, help=help_text)


def _line(info: TokenInfo) -> str:
    """One token: never its digest, the token or a key."""
    cap = "-" if info.cap_usd is None else f"${info.cap_usd:f}"
    state = "ended" if info.ended else "live"
    pending = f"  waiting to be deleted: {info.key_delete_error or 'not tried yet'}"
    waiting = info.ended and info.key_state in ("making", "made")
    return (
        f"run {info.run_id}  connection {info.connection or '-'}  cap {cap}  "
        f"key {info.key_state}  {state}{pending if waiting else ''}\n"
    )


async def _run(args: argparse.Namespace, services: Services) -> int:
    broker = services.get(BrokerService)
    try:
        if args.action == "sweep":
            report = await broker.sweep()
            sys.stdout.write(f"deleted {report.deleted}, failed {report.failed}\n")
            return FAILED if report.failed else 0
        listed = sorted(await broker.listing(), key=lambda info: info.ended)
        sys.stdout.write("".join(_line(info) for info in listed) or "no live tokens\n")
        return 0
    finally:
        await broker.aclose()


broker_command = Command(
    "broker",
    "show the key broker's tokens and keys, or sweep the keys of runs that ended",
    configure=_configure,
    run_async=_run,
)
