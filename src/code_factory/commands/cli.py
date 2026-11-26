"""`code-factory install|uninstall` (the hooks) and `track|untrack` (repositories)."""

import argparse
import asyncio
import sys
from pathlib import Path

from code_factory.commands.models import Scope
from code_factory.commands.service import CommandService
from code_factory.platform.commands import command_services
from code_factory.platform.errors import CodeFactoryError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService


def _configure_hooks(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", choices=[s.value for s in Scope], default=Scope.USER.value)
    parser.add_argument("--project", type=Path, help="the project of a project or local scope")


async def _hooks(args: argparse.Namespace, *, install: bool) -> int:
    async with command_services(args, database=False) as services:
        commands = services.get(CommandService)
        project = args.project or Path.cwd()
        try:
            change = await (commands.install if install else commands.uninstall)(
                Scope(args.scope), project
            )
        except CodeFactoryError as error:
            sys.stderr.write(f"{error}\n")
            return 1
    verb = "installed" if install else "uninstalled"
    sys.stdout.write(f"{verb} capture hooks in {change.path}\n")
    return 0


def _install(args: argparse.Namespace) -> int:
    return asyncio.run(_hooks(args, install=True))


def _uninstall(args: argparse.Namespace) -> int:
    return asyncio.run(_hooks(args, install=False))


def _configure_track(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", nargs="?", type=Path, help="a folder of the repository")


async def _track(args: argparse.Namespace, services: Services) -> int:
    record = await services.get(RepositoryService).track((args.path or Path.cwd()).resolve())
    sys.stdout.write(f"tracking {record.name} at {record.path}\n")
    return 0


async def _untrack(args: argparse.Namespace, services: Services) -> int:
    gone = await services.get(RepositoryService).untrack((args.path or Path.cwd()).resolve())
    sys.stdout.write("untracked\n" if gone else "not tracked\n")
    return 0


commands = (
    Command(
        "install",
        "install the board's hooks into Claude Code settings",
        configure=_configure_hooks,
        run=_install,
    ),
    Command(
        "uninstall",
        "remove the board's hooks from Claude Code settings",
        configure=_configure_hooks,
        run=_uninstall,
    ),
    Command("track", "track a repository", configure=_configure_track, run_async=_track),
    Command(
        "untrack", "stop tracking a repository", configure=_configure_track, run_async=_untrack
    ),
)
