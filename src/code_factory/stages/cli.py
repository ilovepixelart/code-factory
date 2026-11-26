"""`code-factory stage show|observe|rounds`: what the board decided about a ticket and why."""

import argparse
import sys

from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.stages.service import StageService

TICKET_HELP = "CF-<n>"


def _hold_line(hold: dict[str, str] | None) -> str:
    return "none" if hold is None else f"needs {hold['stage']}: {hold['detail']}"


def _configure(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser(
        "show", help="print a ticket's stage, checklist, refusals and hold"
    ).add_argument("ticket", help=TICKET_HELP)
    observe = actions.add_parser("observe", help="read git for tickets and print what changed")
    observe.add_argument(
        "tickets", nargs="*", metavar=TICKET_HELP, help="default: every live ticket"
    )
    actions.add_parser(
        "rounds", help="print a ticket's fix rounds, halts, waits and verdicts"
    ).add_argument("ticket", help=TICKET_HELP)


def _write(*lines: str) -> None:
    sys.stdout.write("".join(f"{line}\n" for line in lines))


async def _show(stages: StageService, ticket: str) -> None:
    found = await stages.assess(ticket)
    _write(
        f"{found.ticket_id} stage {found.stage} "
        f"(derived {found.derived}, declared {found.declared or 'none'})",
        f"facts {'known' if found.facts_known else 'unknown'}, "
        f"observed {found.observed_at or 'never'}",
        f"work done: {'yes' if found.work_done else 'no'}",
        "checklist:",
        *(
            f"  {i.stage}: {'present' if i.present else 'absent'}"
            f"{'' if i.required else ' (optional)'}: {i.detail}"
            for i in found.checklist
        ),
        "refusals:",
        *(f"  {stage}: {why or 'none'}" for stage, why in found.refusals.items()),
        f"hold: {_hold_line(found.hold)}",
    )


async def _observe(stages: StageService, tickets: list[str]) -> None:
    for ticket in tickets:
        await stages.assess(ticket)
    report = await stages.observe(tickets or None)
    _write(
        f"observed {report.observed} tickets, {report.unknown} unreadable",
        *(
            f"{c.ticket_id} {c.stage} {'present' if c.present else 'absent'}"
            for c in report.changes
        ),
    )


async def _rounds(stages: StageService, ticket: str) -> None:
    ledger = await stages.ledger(ticket)
    _write(
        "fix rounds:",
        *(f"  {r.reason} on {r.head[:7]} {r.review}".rstrip() for r in ledger.rounds),
        "halts:",
        *(f"  {h.reason} on {h.head[:7]} after {h.rounds}" for h in ledger.halts),
        "waits on main:",
        *(f"  {w.head[:7]} at {w.step}" for w in ledger.waits),
        "review verdicts:",
        *(f"  {v.outcome} {v.head[:7]} {v.note}".rstrip() for v in ledger.verdicts),
    )


async def _run(args: argparse.Namespace, services: Services) -> int:
    stages = services.get(StageService)
    match args.action:
        case "show":
            await _show(stages, args.ticket)
        case "observe":
            await _observe(stages, args.tickets)
        case _:
            await _rounds(stages, args.ticket)
    return 0


stage_command = Command(
    "stage",
    "show a ticket's stage, observe git for tickets, print fix rounds and review verdicts",
    configure=_configure,
    run_async=_run,
)
