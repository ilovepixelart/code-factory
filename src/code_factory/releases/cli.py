"""`code-factory release draft|show|edit|publish|list`: notes of the repository's releases."""

import argparse
import sys
from pathlib import Path

import anyio

from code_factory.platform.errors import NotFoundError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.releases.adapters import STANDARD_INPUT, read_notes
from code_factory.releases.models import ReleaseView
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService

ACTOR = "owner"
_VERSIONED = {
    "draft": "draft the notes of a version from the merged tickets",
    "show": "print a release's notes",
    "edit": "replace a draft's notes with a file",
    "publish": "make the notes final; the tickets they name leave the board",
}


async def _repository(argument: str | None, services: Services) -> str:
    """The tracked repository the path (default: the current directory) is inside.

    A subfolder or a worktree under a checkout is that checkout; with nested tracked checkouts the
    innermost wins. A folder of no tracked repository is refused: it would name a repository that
    does not exist and the release would be invisible from the real checkout.
    """
    here = Path(await anyio.Path(argument or ".").resolve())
    owners = [
        found
        for found in await services.get(RepositoryService).list()
        if here.is_relative_to(found.path)
    ]
    if not owners:
        msg = f"{here} is not inside a tracked repository: run the command in one, or track it"
        raise NotFoundError(msg)
    return max(owners, key=lambda found: len(found.path)).name


def _configure(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True)
    for name, help_text in _VERSIONED.items():
        action = actions.add_parser(name, help=help_text)
        action.add_argument("version", help="MAJOR.MINOR.PATCH")
        _add_repository(action)
        if name == "edit":
            action.add_argument(
                "--file",
                required=True,
                help=f"the new notes, or {STANDARD_INPUT} for standard input",
            )
    _add_repository(actions.add_parser("list", help="list the repository's releases"))


def _add_repository(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repository",
        metavar="PATH",
        help="a folder inside a tracked repository (default: the current directory)",
    )


def _line(release: ReleaseView) -> str:
    return f"{release.version} {release.state.value} {len(release.tickets)} tickets\n"


async def _run(args: argparse.Namespace, services: Services) -> int:
    releases = services.get(ReleaseService)
    repository = await _repository(args.repository, services)
    version = str(getattr(args, "version", ""))
    match args.action:
        case "draft":
            await releases.draft(repository, version, by=ACTOR)
            sys.stdout.write(f"drafted {repository} {version}\n")
        case "show":
            sys.stdout.write((await releases.get(repository, version)).notes)
        case "edit":
            notes = await read_notes(args.file)
            await releases.edit_notes(repository, version, notes, by=ACTOR)
            sys.stdout.write(f"edited {version}\n")
        case "publish":
            published = await releases.publish(repository, version, by=ACTOR)
            sys.stdout.write(
                f"published {version}: {len(published.tickets)} tickets leave the board\n"
            )
        case _:
            sys.stdout.writelines(_line(release) for release in await releases.list(repository))
    return 0


release_command = Command(
    "release",
    "draft, edit and publish a repository's release notes",
    configure=_configure,
    run_async=_run,
)
