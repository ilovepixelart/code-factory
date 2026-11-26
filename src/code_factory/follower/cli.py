"""`code-factory follower pass|plan`: one pass now, or the queue plan."""

import argparse
import sys

from code_factory.follower.service import FollowerService, QueueService
from code_factory.platform.module import Command
from code_factory.platform.services import Services


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["pass", "plan"])


async def _run(args: argparse.Namespace, services: Services) -> int:
    if args.action == "plan":
        for ticket, note in (await services.get(QueueService).plan()).items():
            sys.stdout.write(f"{ticket}\t{note or 'next up'}\n")
        return 0
    for step, said in (await services.get(FollowerService).run_pass()).steps.items():
        sys.stdout.write(f"{step}: {said}\n")
    return 0


follower_command = Command(
    "follower", "run one board pass, or show the queue plan", configure=_configure, run_async=_run
)
