"""`code-factory halt`, `resume`, `runs list|stop` and the hidden `run-agent`."""

import argparse
import sys
from datetime import UTC, datetime

from code_factory.platform.errors import BadRequestError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.runs.adapters.runner.wrapper import main as run_wrapper
from code_factory.runs.models import RunView
from code_factory.runs.service import RunService
from code_factory.runs.service.reading import view_of

BEGINNING = datetime(1970, 1, 1, tzinfo=UTC)


def _agents(count: int) -> str:
    return f"{count} agent" if count == 1 else f"{count} agents"


async def _halt(args: argparse.Namespace, services: Services) -> int:  # noqa: ARG001
    stopped = await services.get(RunService).stop_all("cli")
    sys.stdout.write(f"stopped {_agents(len(stopped))}; agents are held until resumed\n")
    return 0


async def _resume(args: argparse.Namespace, services: Services) -> int:  # noqa: ARG001
    await services.get(RunService).resume("cli")
    sys.stdout.write("agents may start again\n")
    return 0


def _configure_runs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["list", "stop"])
    parser.add_argument("run", nargs="?", help="stop: the run id")
    parser.add_argument("--ticket", help="list: only this ticket's runs, CF-n")
    parser.add_argument("--active", action="store_true", help="list: only runs with no exit yet")


def _line(*cells: str) -> str:
    return "  ".join(cells).rstrip() + "\n"


def _row(view: RunView) -> str:
    return _line(
        view.id,
        view.ticket_id,
        view.stage,
        view.agent or "-",
        view.state,
        f"{view.started_at:%Y-%m-%d %H:%M:%S}",
    )


async def _list(runs: RunService, args: argparse.Namespace) -> None:
    if args.ticket:
        views = await runs.list_for_ticket(args.ticket)
    else:
        views = sorted(
            (view_of(run) for run in await runs.runs_since(BEGINNING)),
            key=lambda view: view.started_at,
            reverse=True,
        )
    if args.active:
        views = [view for view in views if view.state == "running"]
    sys.stdout.write(_line("RUN", "TICKET", "STAGE", "AGENT", "STATE", "STARTED"))
    for view in views:
        sys.stdout.write(_row(view))


async def _runs(args: argparse.Namespace, services: Services) -> int:
    runs = services.get(RunService)
    if args.action == "stop":
        if not args.run:
            msg = "stop needs a run id: `code-factory runs list --active` shows them"
            raise BadRequestError(msg)
        stopped = await runs.stop(args.run, "cli")
        sys.stdout.write(f"stopped run {stopped.id}\n")
        return 0
    await _list(runs, args)
    return 0


def _configure_run_agent(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("rest", nargs=argparse.REMAINDER, help="<exit file> -- <command...>")


def _run_agent(args: argparse.Namespace) -> int:
    return run_wrapper(args.rest)


halt_command = Command("halt", "stop every agent and hold them until `resume`", run_async=_halt)
resume_command = Command("resume", "let agents start again", run_async=_resume)
runs_command = Command(
    "runs", "list the runs, or stop one", configure=_configure_runs, run_async=_runs
)
run_agent_command = Command(
    "run-agent", argparse.SUPPRESS, configure=_configure_run_agent, run=_run_agent
)
