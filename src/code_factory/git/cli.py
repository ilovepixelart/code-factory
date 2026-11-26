"""`code-factory start|land|save|worktrees|git`: the owner's commands over the git service."""

import argparse
import sys
from pathlib import Path

import anyio

from code_factory.git.models import Conflicted, Landed, Merged, NotMerged, Refused
from code_factory.git.service import GitService
from code_factory.platform.errors import NotFoundError
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService


async def _repository(argument: str | None, services: Services) -> str:
    """The tracked repository the path (default: here) is inside; the innermost wins."""
    here = Path(await anyio.Path(argument or ".").resolve())
    owners = [
        r for r in await services.get(RepositoryService).list() if here.is_relative_to(r.path)
    ]
    if not owners:
        msg = f"{here} is not inside a tracked repository: run the command in one, or track it"
        raise NotFoundError(msg)
    return max(owners, key=lambda found: len(found.path)).name


def _add_repository(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repository", metavar="PATH", help="a folder inside a tracked repository (default: here)"
    )


def landed_line(landed: Landed) -> str:
    """The words the command prints for an outcome."""
    match landed:
        case Merged(url=url):
            return f"merged {url}"
        case NotMerged(why=why):
            return f"not merged: {why}"
        case Refused(why=why):
            return f"refused: {why}"
        case Conflicted(files=files):
            return f"conflicted: {' '.join(files)}"


def _write(text: str) -> None:
    sys.stdout.write(text + "\n")


async def _start(args: argparse.Namespace, services: Services) -> int:
    git, repository = services.get(GitService), await _repository(args.repository, services)
    for ticket_id in args.ids:
        info = await git.start_worktree(repository, ticket_id, owner_by_hand=True)
        _write(f"{info.path} on {info.branch}")
    return 0


async def _land(args: argparse.Namespace, services: Services) -> int:
    git, repository = services.get(GitService), await _repository(args.repository, services)
    failed = False
    for ticket_id in args.ids:
        landed = await git.land(repository, ticket_id)
        _write(f"{ticket_id}: {landed_line(landed)}")
        failed = failed or not isinstance(landed, Merged)
    return 1 if failed else 0


async def _save(args: argparse.Namespace, services: Services) -> int:
    git, repository = services.get(GitService), await _repository(args.repository, services)
    saved = await git.save_work(repository, args.id)
    if saved.not_sent:
        _write(f"{args.id}: saved here at {saved.commit}, not on origin: {saved.not_sent}")
        return 1
    _write(
        f"{args.id}: saved {saved.commit} at refs/wip/{args.id}, "
        f"pushed to origin: {', '.join(saved.sent)}"
    )
    return 0


async def _worktrees(args: argparse.Namespace, services: Services) -> int:
    git, repository = services.get(GitService), await _repository(args.repository, services)
    match args.action:
        case "list":
            for tree in await git.list_trees(repository):
                flags = "" if tree.valid else f" ({tree.orphan})"
                _write(
                    f"{tree.name} {tree.kind.value} {tree.branch} ahead={tree.ahead} "
                    f"uncommitted={tree.uncommitted}{flags}"
                )
        case "remove":
            removed = await git.remove_worktree(repository, args.id)
            _write(
                f"removed {args.id}: branch {removed.branch} "
                f"{'deleted' if removed.branch_deleted else 'kept'}"
            )
        case _:
            stray = await git.reconcile_trees(repository)
            left = await git.empty_trash(repository)
            _write(f"pruned: {len(stray)} folders with no record, {len(left)} left in the trash")
    return 0


async def _git(args: argparse.Namespace, services: Services) -> int:  # noqa: ARG001
    await services.get(GitService).probe()
    _write("git ok")
    return 0


def _ids(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("ids", nargs="+", metavar="ID")
    _add_repository(parser)


def _save_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("id", metavar="ID")
    _add_repository(parser)


def _worktree_args(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("list", "prune"):
        _add_repository(actions.add_parser(name))
    remove = actions.add_parser("remove")
    remove.add_argument("id", metavar="ID")
    _add_repository(remove)


def _probe_args(parser: argparse.ArgumentParser) -> None:
    parser.add_subparsers(dest="action", required=True).add_parser("probe")


COMMANDS = (
    Command("start", "make a ticket's worktree by hand", configure=_ids, run_async=_start),
    Command("land", "merge a ticket's finished branch", configure=_ids, run_async=_land),
    Command(
        "save", "keep a ticket's unfinished work in refs/wip", configure=_save_args, run_async=_save
    ),
    Command(
        "worktrees",
        "list, remove or prune board trees",
        configure=_worktree_args,
        run_async=_worktrees,
    ),
    Command("git", "check this machine's git", configure=_probe_args, run_async=_git),
)
