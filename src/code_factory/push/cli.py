"""`code-factory push ntfy|webhook <address>` sets where messages go; `push off` stops them."""

import argparse
import sys

from code_factory.platform.errors import BadRequestError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.push.service import PushService


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("format", choices=["ntfy", "webhook", "off"])
    parser.add_argument("address", nargs="?", default="")


async def _run(args: argparse.Namespace, services: Services) -> int:
    push = services.get(PushService)
    if args.format == "off":
        await push.clear_target()
        sys.stdout.write("pushing nothing\n")
        return 0
    if not args.address:
        msg = f"name the address: code-factory push {args.format} <address>"
        raise BadRequestError(msg)
    target = await push.set_target(args.format, args.address)
    sys.stdout.write(f"pushing to {target.url} as {target.format}\n")
    return 0


push_command = Command(
    "push", "push what waits on you to ntfy or a webhook", configure=_configure, run_async=_run
)
