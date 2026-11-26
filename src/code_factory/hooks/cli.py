"""The owner's small commands: sign-out, audit export, error and recall."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from code_factory.hooks.ports import Checkouts
from code_factory.hooks.service import HookService
from code_factory.platform.errors import CodeFactoryError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.platform.text import is_iso_date


def _day(text: str) -> str:
    if not is_iso_date(text):
        msg = f'"{text}" is not a day as YYYY-MM-DD'
        raise argparse.ArgumentTypeError(msg)
    return text


async def _sign_out(args: argparse.Namespace, services: Services) -> int:  # noqa: ARG001
    ended = await services.get(HookService).sign_out()
    noun = "session" if ended == 1 else "sessions"
    sys.stdout.write(
        f"signed out {ended} {noun}; a browser signed in with the owner token's link stays signed"
        " in until the owner token changes\n"
    )
    return 0


def _configure_audit(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["export"])
    parser.add_argument("--since", type=_day, required=True, help="the first day, YYYY-MM-DD")


async def _audit(args: argparse.Namespace, services: Services) -> int:
    for line in await services.get(HookService).audit_export(args.since):
        sys.stdout.write(json.dumps(line, separators=(", ", ": "), ensure_ascii=True) + "\n")
    return 0


def _configure_error(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repository", help="the tracked repository, the working folder's by default"
    )


def _report() -> object:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


async def _error(args: argparse.Namespace, services: Services) -> int:
    repository = args.repository or await _folder_repository(services)
    if repository is None:
        sys.stderr.write("the working folder is in no tracked repository: pass --repository\n")
        return 2
    try:
        reported = await services.get(HookService).report_error(
            repository, _report(), datetime.now(UTC)
        )
    except CodeFactoryError as error:
        sys.stderr.write(f"{error}\n")
        return 2
    line = (
        reported.ticket_id
        if reported.created
        else f"{reported.ticket_id}: reported {reported.count} times"
    )
    sys.stdout.write(line + "\n")
    return 0


async def _folder_repository(services: Services) -> str | None:
    checkout = await services.get(Checkouts).of(str(Path.cwd()))
    return checkout.repository if checkout else None


async def _recall(args: argparse.Namespace, services: Services) -> int:  # noqa: ARG001
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        cwd = str(payload.get("cwd") or Path.cwd())
        recalled = await services.get(HookService).recall(cwd=cwd, actor=None)
    except Exception:  # noqa: BLE001  # recall never fails the owner's session
        return 0
    if recalled is not None:
        sys.stdout.write(recalled.text)
    return 0


commands = (
    Command("sign-out", "end every owner browser session", run_async=_sign_out),
    Command(
        "audit", "export who did what on the tickets", configure=_configure_audit, run_async=_audit
    ),
    Command(
        "error",
        "file a production error report as a bug ticket",
        configure=_configure_error,
        run_async=_error,
    ),
    Command("recall", "print what a session starting in this folder is given", run_async=_recall),
)
