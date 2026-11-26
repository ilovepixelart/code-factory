"""Which repository and branch a working folder belongs to, from the contents of git's files.

The rules are over text and paths; reading the files is the adapter's job.
"""

from pathlib import PurePosixPath

TREES = ".code-factory/worktrees"
POINTER = "gitdir: "
_HEAD_REF = "ref: refs/heads/"
_DETACHED_CHARS = 8


def tree_checkout(path: PurePosixPath, trees: str = TREES) -> PurePosixPath:
    """What `path` stands for as a repository: the checkout whose board run tree it is in.

    A run tree is `<checkout>/<trees>/<name>`, found at or above `path`, the innermost first. A
    folder in no run tree stands for itself.
    """
    for folder in (path, *path.parents):
        checkout = folder.parent.parent.parent
        if folder.parent == checkout / trees:
            return checkout
    return path


def pointer_target(text: str, root: PurePosixPath) -> PurePosixPath:
    """The git directory a `.git` pointer file names; relative ones are relative to `root`."""
    pointer = text.strip().removeprefix(POINTER)
    return root / pointer


def gitdir_of(text: str, root: PurePosixPath) -> PurePosixPath | None:
    """The git directory a `.git` pointer file names; None when it is no `gitdir:` pointer."""
    pointer = text.strip()
    if not pointer.startswith(POINTER):
        return None
    return root / pointer.removeprefix(POINTER)


def main_of_worktree_gitdir(target: PurePosixPath) -> PurePosixPath | None:
    """The main checkout of a linked worktree's git directory `<main>/.git/worktrees/<name>`."""
    parent = target.parent
    if parent.name == "worktrees" and parent.parent.name == ".git":
        return parent.parent.parent
    return None


def branch_of_head(text: str) -> str:
    """The branch a `HEAD` file names, or the first 8 characters of a detached revision."""
    head = text.strip()
    if head.startswith(_HEAD_REF):
        return head.removeprefix(_HEAD_REF)
    return head[:_DETACHED_CHARS]


def folder_name(cwd: str) -> str:
    """The last segment of a folder: what a session outside any repository is grouped under."""
    return PurePosixPath(cwd).name if cwd else ""
