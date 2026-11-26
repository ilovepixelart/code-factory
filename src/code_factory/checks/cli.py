"""`code-factory checks run|show|list|main|verify|flaky|forget-cache|reconcile`."""

import argparse
import asyncio
import sys

from code_factory.checks.models import Scope, ViewState
from code_factory.checks.service import CheckService
from code_factory.platform.module import Command
from code_factory.platform.services import Services

STREAM_POLL_S = 0.5
EXIT_FAILED = 1
EXIT_NO_VERDICT = 2


def _configure(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True)
    run = actions.add_parser("run", help="run the checks of a ticket here, streaming the log")
    run.add_argument("ticket", help="CF-<n>")
    run.add_argument("--scope", choices=[s.value for s in Scope], default=Scope.REACHED.value)
    show = actions.add_parser("show", help="print a ticket's latest check and a page of its log")
    show.add_argument("ticket", help="CF-<n>")
    show.add_argument("--log-offset", type=int, default=0, help="byte offset into the log")
    listed = actions.add_parser("list", help="print the recent runs")
    listed.add_argument("ticket", nargs="?", help="CF-<n> or main")
    listed.add_argument("--limit", type=int, default=20)
    main = actions.add_parser("main", help="run [checks] main on a repository's default branch")
    main.add_argument("repository")
    main.add_argument("--tip", help="a commit to check (default: the default branch's tip)")
    verify = actions.add_parser("verify", help="run [release] verify of a repository now")
    verify.add_argument("repository")
    flaky = actions.add_parser("flaky", help="attach a bug to the flaky failure of a ticket")
    flaky.add_argument("ticket", help="CF-<n>")
    flaky.add_argument("bug", help="CF-<m>, a bug ticket")
    forget = actions.add_parser("forget-cache", help="remove a ticket's build cache")
    forget.add_argument("ticket", help="CF-<n>")
    actions.add_parser("reconcile", help="mark runs of a stopped process lost; remove strays")


def _write(*lines: str) -> None:
    sys.stdout.write("".join(f"{line}\n" for line in lines))


async def _stream(checks: CheckService, check_id: int) -> int:
    """Run the check here and print its log as it grows; the exit code of the verdict."""
    task = asyncio.create_task(checks.run_now(check_id))
    offset = 0
    while not task.done():
        await asyncio.wait({task}, timeout=STREAM_POLL_S)
        text, offset = await checks.log_chunk(check_id, offset)
        sys.stdout.write(text)
    row = await task
    text, offset = await checks.log_chunk(check_id, offset)
    sys.stdout.write(text)
    verdict = row.verdict.value if row.verdict is not None else row.state.value
    _write(f"check {check_id}: {verdict}")
    if verdict == "passed":
        return 0
    return EXIT_FAILED if verdict == "failed" else EXIT_NO_VERDICT


async def _show(checks: CheckService, ticket: str, offset: int) -> None:
    view = await checks.latest(ticket, log_offset=offset)
    if view.state is ViewState.NONE:
        _write(f"{ticket}: no check yet")
        return
    _write(
        f"{ticket}: {view.state.value} on {view.commit[:7]}"
        f"{'' if view.head_current else ' (not the branch tip)'}",
        f"exit code: {view.exit_code if view.exit_code is not None else 'none'}",
        f"failed step: {view.failed_step or 'none'}",
        f"reason: {view.reason or 'none'}",
        f"log: {view.log_size} bytes, from {view.log_offset} to {view.next_offset}",
    )
    sys.stdout.write(view.log_tail)


async def _list(checks: CheckService, ticket: str | None, limit: int) -> None:
    for row in await checks.recent_runs(limit, ticket):
        code = "-" if row.exit_code is None else str(row.exit_code)
        _write(
            f"{row.id} {row.subject} {row.scope.value} {row.commit[:7]} {row.state.value} "
            f"{'-' if row.verdict is None else row.verdict.value} exit {code}"
        )


async def _main(checks: CheckService, repository: str, tip: str | None) -> int:
    check_id = await checks.start_main(repository, tip)
    return await _stream(checks, check_id)


async def _verify(checks: CheckService, repository: str) -> int:
    release = await checks.due_verify(repository) or await checks.newest_release(repository)
    if release is None:
        _write(f"{repository}: no release to verify")
        return 0
    record = await checks.verify(repository, release)
    _write(f"release {record.release}: exit {record.exit_code}, log {record.log}")
    return 0 if record.exit_code == 0 else EXIT_FAILED


async def _run(args: argparse.Namespace, services: Services) -> int:
    checks = services.get(CheckService)
    match args.action:
        case "run":
            check_id = await checks.start(args.ticket, Scope(args.scope), by="owner")
            return await _stream(checks, check_id)
        case "show":
            await _show(checks, args.ticket, args.log_offset)
        case "list":
            await _list(checks, args.ticket, args.limit)
        case "main":
            return await _main(checks, args.repository, args.tip)
        case "verify":
            return await _verify(checks, args.repository)
        case "flaky":
            _write(await checks.attach_flaky(args.ticket, args.bug, "owner"))
        case "forget-cache":
            await checks.forget_cache(args.ticket)
        case _:
            _write(f"{await checks.reconcile()} runs lost")
    return 0


checks_command = Command(
    name="checks",
    help="run and read the board's checks",
    configure=_configure,
    run_async=_run,
)
