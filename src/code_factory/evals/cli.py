"""Record, report and compare completed suite runs."""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from code_factory.evals.models import EvalRecord
from code_factory.evals.service import EvalService
from code_factory.platform.errors import BadRequestError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["record", "report", "compare"])
    parser.add_argument("set_name", metavar="NAME", help="the task set")
    parser.add_argument(
        "--repository", help="a tracked repository, the current folder's by default"
    )
    parser.add_argument("--agent", action="append", default=[], help="compare: name two agents")
    parser.add_argument(
        "--input", type=Path, help="record: JSON receipt for a completed evaluation"
    )


def _receipt(path: Path, repository: str, name: str) -> EvalRecord:
    try:
        raw = json.loads(path.read_bytes())
    except OSError as error:
        msg = f"could not read the evaluation receipt: {error.strerror}"
        raise BadRequestError(msg) from None
    except ValueError:
        msg = "the evaluation receipt must be valid UTF-8 JSON"
        raise BadRequestError(msg) from None
    if not isinstance(raw, dict) or {"id", "repository", "set_name"} & raw.keys():
        msg = "the receipt must be a JSON object without id, repository or set_name"
        raise BadRequestError(msg)
    if not raw.get("receipt") or not isinstance(raw.get("recorded_at"), str):
        msg = "the receipt must include a source receipt ID and a timezone-aware recorded_at"
        raise BadRequestError(msg)
    try:
        record = EvalRecord.model_validate(
            raw | {"repository": repository, "set_name": name}, extra="forbid"
        )
    except ValidationError as error:
        [first, *_] = error.errors(include_url=False, include_context=False, include_input=False)
        field = ".".join(str(part) for part in first["loc"])
        msg = f"invalid evaluation receipt at {field or 'result'}: {first['msg']}"
        raise BadRequestError(msg) from None
    if record.recorded_at > datetime.now(UTC):
        msg = "recorded_at is after the current time. Use the finished evaluation's timestamp."
        raise BadRequestError(msg)
    return record


async def _run(args: argparse.Namespace, services: Services) -> int:
    evals = services.get(EvalService)
    repository = args.repository or Path.cwd().name
    if args.action == "record":
        if args.input is None or args.agent:
            msg = "record needs --input and takes no --agent. Name the agent in the receipt setup."
            raise BadRequestError(msg)
        await services.get(RepositoryService).get(repository)
        receipt = await asyncio.to_thread(_receipt, args.input, repository, args.set_name)
        record_id = await evals.record(receipt)
        sys.stdout.write(f"evaluation recorded as {record_id}\n")
        return 0
    if args.input is not None:
        msg = "--input is for eval record"
        raise BadRequestError(msg)
    if args.action == "report":
        lines = await evals.report(repository, args.set_name)
        sys.stdout.write("\n".join(lines or [f"no runs recorded for {args.set_name}"]) + "\n")
        return 0
    result = await evals.compare(repository, args.set_name, args.agent)
    sys.stdout.write("\n".join(result.lines) + "\n")
    return 1 if result.loses else 0


eval_command = Command(
    "eval", "record, report or compare completed eval runs", configure=_configure, run_async=_run
)
