"""Where board trees live, which git options guard them, and whether their git folders are intact.

A run writes its tree, so everything git reads there is data a run may have forged: the board runs
git in a tree only after `validate_tree` accepts what an adapter read of it.
"""

import re
from pathlib import PurePosixPath

from code_factory.git.models import FolderSnapshot, Redirected, TreeFolders, TreeKind, TreeRecord

TREES = ".code-factory/worktrees"
CLONE_TOKEN_FILE = "code-factory-clone"  # noqa: S105  # a file name inside a clone's .git
TRASH = "code-factory-trash"
REDIRECTED = (
    "its tree's .git no longer points at the git folder the board made for it, so the board "
    "ran no git there"
)
WORKTREE_GUARDS = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "diff.ignoreSubmodules=all",
)
_WORK_TREE_DIFFS = frozenset({"status", "diff", "diff-index", "diff-files"})
_TOKEN = re.compile(r"[0-9a-f]{32}")


def guarded(args: list[str], *, in_tree: bool) -> list[str]:
    """The words of a git command as the board runs it.

    In a board tree the guards come first, and the four commands that compare the work tree take
    `--ignore-submodules=all`, which outranks a submodule's own setting.
    """
    if not in_tree or not args:
        return list(args)
    command, rest = args[0], args[1:]
    submodules = ["--ignore-submodules=all"] if command in _WORK_TREE_DIFFS else []
    return [*WORKTREE_GUARDS, command, *submodules, *rest]


def fast_forward_merge(rev: str) -> list[str]:
    """A fast-forward merge to `rev` that runs no hook or fsmonitor of the repository's own."""
    return [*WORKTREE_GUARDS[:4], "merge", "-q", "--ff-only", "--end-of-options", rev]


def board_tree_of(path: str) -> tuple[str, str] | None:
    """The checkout and the tree `path` is in.

    The innermost `<checkout>/.code-factory/worktrees/<name>` at or above `path`.
    """
    here = PurePosixPath(path)
    for folder in (here, *here.parents):
        trees = folder.parent
        checkout = trees.parent.parent
        if checkout / TREES == trees and folder != trees:
            return str(checkout), str(folder)
    return None


def named_folder(text: str | None, prefix: str) -> str | None:
    r"""The folder `text` names when it is exactly `<prefix><absolute folder>\n`, else `None`."""
    if text is None or not text.startswith(prefix) or not text.endswith("\n"):
        return None
    folder = text.removeprefix(prefix).removesuffix("\n")
    return folder if folder.startswith("/") and "\n" not in folder else None


def _worktree(snapshot: FolderSnapshot) -> TreeFolders | None:
    admin = named_folder(snapshot.dot_git_text, "gitdir: ")
    if admin is None:
        return None
    dot_git = f"{snapshot.resolved_path}/.git"
    held = (
        snapshot.dot_git_kind == "file"
        and snapshot.dot_git_resolved == dot_git
        and snapshot.admin_resolved == admin
        and str(PurePosixPath(admin).parent) == f"{snapshot.common_dir}/worktrees"
        and snapshot.gitdir_text == f"{dot_git}\n"
        and snapshot.commondir_text == "../..\n"
    )
    if not held:
        return None
    return TreeFolders(
        worktree=snapshot.resolved_path, admin=admin, common=snapshot.common_dir, is_clone=False
    )


def _names_alternates(snapshot: FolderSnapshot) -> bool:
    """Whether the alternates file is a link, names a folder or is not read as empty."""
    path = f"{snapshot.resolved_path}/.git/objects/info/alternates"
    if snapshot.alternates_resolved != path:
        return True
    if snapshot.alternates_text is None:
        return snapshot.alternates_exists
    return bool(snapshot.alternates_text.strip())


def _clone(snapshot: FolderSnapshot, record: TreeRecord) -> TreeFolders | None:
    dot_git = f"{snapshot.resolved_path}/.git"
    token = (snapshot.token_text or "").removesuffix("\n")
    held = (
        snapshot.dot_git_kind == "dir"
        and snapshot.dot_git_resolved == dot_git
        and not snapshot.commondir_exists
        and snapshot.info_resolved == f"{dot_git}/objects/info"
        and not _names_alternates(snapshot)
        and _TOKEN.fullmatch(token) is not None
        and token == record.token
    )
    if not held:
        return None
    return TreeFolders(
        worktree=snapshot.resolved_path, admin=dot_git, common=dot_git, is_clone=True
    )


def validate_tree(snapshot: FolderSnapshot, record: TreeRecord | None) -> TreeFolders | Redirected:
    r"""The git folders of a tree when they are exactly what the board made, else `Redirected`.

    A worktree: `.git` reads `gitdir: <resolved admin folder>\\n`, the admin folder is directly
    under `<common>/worktrees`, its `gitdir` and `commondir` read as `git worktree add` writes
    them. A clone: `.git` is a real folder with no `commondir`, no alternates naming a folder, a
    real `objects/info`, and the token in it equals the recorded one. Neither may have a `.git`
    of its own between the path and the tree.
    """
    found = None
    if record is not None and not snapshot.nested_git:
        found = _clone(snapshot, record) if record.kind is TreeKind.CLONE else _worktree(snapshot)
    return found or Redirected(reason=REDIRECTED)


def kept_paths(folders: TreeFolders) -> list[str]:
    """What a run's sandbox may not write: the files the board's git reads outside it."""
    if folders.is_clone:
        return [
            f"{folders.common}/config",
            f"{folders.common}/hooks",
            f"{folders.common}/objects/info/alternates",
            f"{folders.admin}/HEAD",
        ]
    return [
        f"{folders.worktree}/.git",
        f"{folders.admin}/commondir",
        f"{folders.admin}/gitdir",
        f"{folders.admin}/config.worktree",
        f"{folders.common}/config",
        f"{folders.common}/hooks",
        f"{folders.admin}/HEAD",
    ]
