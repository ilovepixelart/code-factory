"""`code-factory delivery`: pull requests, events, why a merge waits, one pass, intake, probe."""

import argparse
import sys

from code_factory.delivery.service import DeliveryService
from code_factory.platform.module import Command
from code_factory.platform.services import Services


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["pulls", "events", "why", "pass", "intake", "merge"])
    parser.add_argument("ticket", nargs="?", help="events, why, merge: the ticket, CF-n")
    parser.add_argument("--repository", help="intake: only this repository")


async def _pulls(delivery: DeliveryService, args: argparse.Namespace) -> int:  # noqa: ARG001
    for pull in await delivery.open_pulls():
        sys.stdout.write(
            f"{pull.ticket_id}\t{pull.state}\t{pull.ci}\t{pull.merge_state or '-'}"
            f"\t{pull.head[:7]}\t{pull.url}\n"
        )
    return 0


async def _events(delivery: DeliveryService, args: argparse.Namespace) -> int:
    for event in (await delivery.events([args.ticket])).get(args.ticket, []):
        retry = event.retry_at.isoformat() if event.retry_at else "final"
        sys.stdout.write(
            f"{event.at.isoformat()}\t{event.kind}\t{event.head[:7]}\t{event.reason}\t{retry}\n"
        )
    return 0


async def _why(delivery: DeliveryService, args: argparse.Namespace) -> int:
    verdict = await delivery.why(args.ticket)
    sys.stdout.write("ready\n" if verdict.ready else f"{verdict.reason}\n")
    return 0 if verdict.ready else 1


async def _merge(delivery: DeliveryService, args: argparse.Namespace) -> int:
    merged = await delivery.merge(args.ticket, by="cli")
    sys.stdout.write(f"merged {merged.url} at {merged.head[:7]}\n")
    return 0


async def _pass(delivery: DeliveryService, args: argparse.Namespace) -> int:  # noqa: ARG001
    for step, said in (await delivery.run_pass()).steps.items():
        sys.stdout.write(f"{step}: {said}\n")
    return 0


async def _intake(delivery: DeliveryService, args: argparse.Namespace) -> int:
    made = await delivery.poll_intake(args.repository)
    sys.stdout.write(f"imported {len(made)}: {', '.join(made) or 'none'}\n")
    return 0


_ACTIONS = {
    "pulls": _pulls, "events": _events, "why": _why, "merge": _merge, "pass": _pass,
    "intake": _intake,
}  # fmt: skip


async def _run(args: argparse.Namespace, services: Services) -> int:
    if args.action in {"events", "why", "merge"} and not args.ticket:
        sys.stderr.write(f"delivery {args.action} needs a ticket, CF-n\n")
        return 2
    return await _ACTIONS[args.action](services.get(DeliveryService), args)


delivery_command = Command(
    "delivery",
    "pull requests, the board merge and issue intake",
    configure=_configure,
    run_async=_run,
)
