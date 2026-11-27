"""`code-factory follower pass|plan`: one pass now, or the queue plan."""

import argparse
import sys

from code_factory.follower.service import FollowerService, QueueService
from code_factory.platform.module import Command
from code_factory.platform.services import Services


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["pass", "plan"])


async def _plan(services: Services) -> None:
    for ticket, note in (await services.get(QueueService).plan()).items():
        sys.stdout.write(f"{ticket}\t{note or 'next up'}\n")


async def _pass(services: Services) -> None:
    for step, said in (await services.get(FollowerService).run_pass()).steps.items():
        sys.stdout.write(f"{step}: {said}\n")


async def _run(args: argparse.Namespace, services: Services) -> int:
    await (_plan if args.action == "plan" else _pass)(services)
    return 0


follower_command = Command(
    "follower", "run one board pass, or show the queue plan", configure=_configure, run_async=_run
)
