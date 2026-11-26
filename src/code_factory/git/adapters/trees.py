"""Making and removing the places agents work: clones and linked worktrees."""

import os
import secrets
import shutil
from pathlib import Path

from code_factory.git.adapters.folders import exists, threaded
from code_factory.git.adapters.runner import WRITE_TIMEOUT_S, GitRunner
from code_factory.git.rules.branches import is_commit_id
from code_factory.git.rules.folders import CLONE_TOKEN_FILE, TRASH, TREES
from code_factory.platform.errors import ConflictError, UnavailableError

_REFSPECS = (
    "+refs/heads/*:refs/heads/*",
    "+refs/remotes/*:refs/remotes/*",
    "+refs/tags/*:refs/tags/*",
)


def new_token() -> str:
    """32 lowercase hex characters."""
    return secrets.token_hex(16)


def _write_token(tree: Path, token: str) -> None:
    (tree / ".git" / CLONE_TOKEN_FILE).write_text(f"{token}\n", encoding="utf-8")


def _hold_alternates(tree: Path) -> None:
    info = tree / ".git" / "objects" / "info"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        os.close(os.open(info / "alternates", flags, 0o644))
    except FileExistsError:
        return


async def make_clone(runner: GitRunner, root: Path, tree: Path, start: str, token: str) -> None:
    """A repository of its own holding the main repository's refs, checked out at `start`.

    Fetched by git's own transport (no hardlinks, no alternates); a commit id is fetched by id. The
    token goes into `.git` and the empty alternates file is made last.
    """
    await threaded(lambda: tree.parent.mkdir(parents=True, exist_ok=True))
    await runner.checked(root, ["init", "--quiet", str(tree)], timeout_s=WRITE_TIMEOUT_S)
    await threaded(lambda: _write_token(tree, token))
    by_id = [start] if is_commit_id(start) else []
    fetch = ["fetch", "--quiet", "--no-tags", "--update-head-ok", str(root), *_REFSPECS, *by_id]
    await runner.checked(tree, fetch, timeout_s=WRITE_TIMEOUT_S, clone=True)
    await runner.checked(
        tree,
        ["checkout", "--quiet", "--end-of-options", start],
        timeout_s=WRITE_TIMEOUT_S,
        clone=True,
    )
    await threaded(lambda: _hold_alternates(tree))


async def make_worktree(
    runner: GitRunner, root: Path, tree: Path, branch: str, base: str | None
) -> None:
    """`worktree add -q --no-track -b branch tree base`; with no `base` the branch exists already.

    The caller holds the repository's ref lock.
    """
    if await exists(tree):
        msg = f"{tree} exists"
        raise ConflictError(msg)
    args = ["worktree", "add", "-q", "--no-track"]
    args += ["-b", branch, str(tree), base] if base is not None else [str(tree), branch]
    await runner.checked(root, args, timeout_s=WRITE_TIMEOUT_S)


async def make_snapshot(runner: GitRunner, root: Path, tree: Path, commit: str) -> None:
    """A detached worktree of `commit`."""
    args = ["worktree", "add", "-q", "--detach", str(tree), commit]
    async with runner.ref_lock(root):
        await runner.checked(root, args, timeout_s=WRITE_TIMEOUT_S)


def _directly_in_trees(checkout: Path, tree: Path) -> bool:
    folder = checkout / TREES

    def plain(path: Path) -> bool:
        return path.is_dir() and not path.is_symlink()

    return bool(
        plain(checkout / ".code-factory")
        and plain(folder)
        and tree.parent == folder
        and Path(os.path.realpath(tree.parent)) == Path(os.path.realpath(folder))
    )


def _discard(checkout: Path, common: Path, tree: Path) -> None:
    if not os.path.lexists(tree):
        return
    if not _directly_in_trees(checkout, tree):
        msg = (
            f"{tree} is not directly in {checkout}'s folder of board trees, reached by no link: "
            "the board deletes trees only there"
        )
        raise ConflictError(msg)
    trash = common / TRASH
    trash.mkdir(exist_ok=True)
    if trash.is_symlink():
        msg = f"{trash} is a link"
        raise UnavailableError(msg)
    aside = trash / f"{tree.name}.{secrets.token_hex(8)}"
    tree.rename(aside)
    _remove_entry(aside)


def _remove_entry(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)  # does not follow links inside
    else:
        path.unlink()


async def remove_tree(checkout: Path, common: Path, tree: Path) -> None:
    """Rename `tree` into the trash folder of the git folder, then delete it without links.

    Only a tree directly in the trees folder, reached by no link. A tree already gone is fine.
    """
    await threaded(lambda: _discard(checkout, common, tree), WRITE_TIMEOUT_S)


def _empty_trash(common: Path) -> list[tuple[str, str]]:
    trash = common / TRASH
    if trash.is_symlink() or not trash.is_dir():
        return []
    left = []
    for entry in trash.iterdir():
        try:
            _remove_entry(entry)
        except OSError as error:
            left.append((str(entry), error.strerror or str(error)))
    return left


async def empty_trash(common: Path) -> list[tuple[str, str]]:
    """Delete what a stop left in the trash; the entries that could not go, with the reason."""
    return await threaded(lambda: _empty_trash(common), WRITE_TIMEOUT_S)


def _exclude(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{TREES}/\n"
    held = path.read_text(encoding="utf-8") if path.exists() else ""
    if TREES in held:
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(("" if not held or held.endswith("\n") else "\n") + line)


async def exclude_trees_folder(runner: GitRunner, root: Path) -> None:
    """Keep the trees folder out of git's view of the checkout, once, creating `info` if needed."""
    named = await runner.checked(root, ["rev-parse", "--git-path", "info/exclude"])
    await threaded(lambda: _exclude(root / named))
