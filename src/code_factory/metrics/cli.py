"""`code-factory metrics times|refresh|forecast|factory`: the reports as plain text."""

import argparse
import sys

from code_factory.metrics.models import RefreshResult, Yield
from code_factory.metrics.service import MetricsService
from code_factory.platform.module import Command
from code_factory.platform.services import Services

_ACTIONS = {
    "times": "the gate step times, minutes per column and reverts",
    "refresh": "read git now and update the merge ledger",
    "forecast": "when the open tickets are done",
    "factory": "the yield of each agent and model on merged work",
}


def _configure(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True)
    for name, help_text in _ACTIONS.items():
        action = actions.add_parser(name, help=help_text)
        action.add_argument("--repository", metavar="NAME", help="a tracked repository's name")
        if name == "times":
            action.add_argument("--last", type=int, default=50, help="runs to read (default 50)")
        if name == "forecast":
            action.add_argument("--open", type=int, dest="open_tickets", help="tickets still open")


def _refresh_line(result: RefreshResult) -> str:
    return (
        f"{result.repository}: {result.seen} merges, {result.inserted} new, "
        f"{result.reverted} reverted, {result.cuts} branch cuts\n"
    )


def _yield_table(rows: list[Yield]) -> str:
    lines = ["agent  model  runs  unfinished  merged  held  end-to-end  median-intake  cost"]
    for y in rows:
        intake = "-" if y.median_intake_to_merge is None else f"{y.median_intake_to_merge:.0f}"
        cost = "-" if y.cost is None else f"{y.cost:.2f}"
        lines.append(
            f"{y.agent or '-'}  {y.model or '-'}  {y.runs}  {y.unfinished}  {y.merged}  "
            f"{y.held}  {y.end_to_end}  {intake}  {cost}"
        )
    return "\n".join(lines) + "\n"


async def _run(args: argparse.Namespace, services: Services) -> int:
    metrics = services.get(MetricsService)
    out = sys.stdout
    match args.action:
        case "times":
            out.write((await metrics.times_report(args.last, args.repository)).text)
        case "refresh":
            out.writelines(_refresh_line(r) for r in await metrics.refresh(args.repository))
        case "forecast":
            found = await metrics.forecast(args.open_tickets, args.repository)
            out.write(f"open: {found.open}\n")
            if found.p50 is None:
                out.write("no ticket reached review in the last 56 days: no forecast\n")
            else:
                out.write(f"done in {found.p50} days (50%), {found.p85} days (85%)\n")
        case _:
            out.write(_yield_table(await metrics.factory(args.repository)))
    return 0


metrics_command = Command(
    "metrics",
    "reports on how work moves: step times, the merge ledger, forecast and yields",
    configure=_configure,
    run_async=_run,
)
