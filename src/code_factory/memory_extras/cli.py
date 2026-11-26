"""`code-factory memory review`: the review queue, the pairs and the consolidation proposals."""

import argparse
import json
import sys

from code_factory.memory_extras.models import MergeProposal, PairRecord, Record, RetireProposal
from code_factory.memory_extras.rules import queue_reasons
from code_factory.memory_extras.service import MemoryExtrasService
from code_factory.platform.errors import NotFoundError
from code_factory.platform.module import Command
from code_factory.platform.services import Services


def _configure(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True)
    review = actions.add_parser(
        "review", help="list what waits for the owner: the review queue, pairs and consolidations"
    )
    review.add_argument(
        "--repository", metavar="NAME", help="a tracked repository (default: every one)"
    )
    review.add_argument("--json", action="store_true", help="print the three lists as JSON")


def _queue_line(record: Record, today: str) -> str:
    reasons = ", ".join(queue_reasons(record, today))
    return f"{record.repository} {record.id} due {record.review_due}: {reasons}\n"


def _pair_line(pair: PairRecord) -> str:
    said = "may contradict" if pair.contradicts else "on one subject"
    return f"{pair.repository} {said}: {pair.one} and {pair.other} ({', '.join(pair.terms)})\n"


def _proposal_line(proposal: MergeProposal | RetireProposal) -> str:
    if isinstance(proposal, MergeProposal):
        return f"{proposal.repository} merge {proposal.id} into {proposal.into}\n"
    return f"{proposal.repository} retire {proposal.id}: {proposal.reason}\n"


def _text(
    queue: list[Record],
    pairs: list[PairRecord],
    proposals: list[MergeProposal | RetireProposal],
    today: str,
) -> str:
    sections = [
        ("review queue:\n", [_queue_line(r, today) for r in queue]),
        ("pairs:\n", [_pair_line(p) for p in pairs]),
        ("proposals:\n", [_proposal_line(p) for p in proposals]),
    ]
    shown = [heading + "".join(lines) for heading, lines in sections if lines]
    return "".join(shown) or "nothing to review\n"


async def _run(args: argparse.Namespace, services: Services) -> int:
    memory = services.get(MemoryExtrasService)
    known = await memory.repositories()
    if args.repository is not None and args.repository not in known:
        msg = f"{args.repository} is not a tracked repository"
        raise NotFoundError(msg)
    queue: list[Record] = []
    pairs: list[PairRecord] = []
    proposals: list[MergeProposal | RetireProposal] = []
    for name in [args.repository] if args.repository is not None else known:
        queue += await memory.review_queue(name)
        pairs += await memory.pairs(name)
        proposals += await memory.proposals(name)
    if args.json:
        answer = {
            "review_queue": [r.model_dump(mode="json") for r in queue],
            "pairs": [p.model_dump(mode="json") for p in pairs],
            "proposals": [p.model_dump(mode="json") for p in proposals],
        }
        sys.stdout.write(json.dumps(answer, indent=2) + "\n")
    else:
        sys.stdout.write(_text(queue, pairs, proposals, memory.today()))
    return 0


memory_command = Command(
    "memory",
    "review what memory waits on the owner for",
    configure=_configure,
    run_async=_run,
)
