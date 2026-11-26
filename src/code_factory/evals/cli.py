"""`code-factory eval report|compare NAME` over the recorded suite runs."""

import argparse
import sys
from pathlib import Path

from code_factory.evals.service import EvalService
from code_factory.platform.module import Command
from code_factory.platform.services import Services


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["report", "compare"])
    parser.add_argument("set_name", metavar="NAME", help="the task set")
    parser.add_argument(
        "--repository", help="a tracked repository, the current folder's by default"
    )
    parser.add_argument("--agent", action="append", default=[], help="compare: name two agents")


async def _run(args: argparse.Namespace, services: Services) -> int:
    evals = services.get(EvalService)
    repository = args.repository or Path.cwd().name
    if args.action == "report":
        lines = await evals.report(repository, args.set_name)
        sys.stdout.write("\n".join(lines or [f"no runs recorded for {args.set_name}"]) + "\n")
        return 0
    result = await evals.compare(repository, args.set_name, args.agent)
    sys.stdout.write("\n".join(result.lines) + "\n")
    return 1 if result.loses else 0


eval_command = Command(
    "eval", "report or compare recorded eval runs", configure=_configure, run_async=_run
)
