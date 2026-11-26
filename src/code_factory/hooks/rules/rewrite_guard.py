"""The shell commands that rewrite a commit origin already has.

The board pushes a ticket's branch as soon as a commit exists on it, so an amend, a rebase or a
reset past that commit, a forced push, a pull that rebases, or deleting or moving the branch,
strands what it pushed. The words of a command are read as a shell reads them (quotes, chains,
`-C`, `cd`, `sh -c`); what the branch holds is read by the caller and passed in as a
`BranchState`.

The files of this folder import only each other and nothing from the standard library: the hook
process starts them with `python -I -S` (no site packages), and every import costs start time on
each shell command of a run.
"""

from code_factory.hooks.rules import git_words, shell

Action = git_words.Action
AMEND = git_words.AMEND
FORCE = git_words.FORCE
PULL_REBASE = git_words.PULL_REBASE
REBASE_ROOT = git_words.REBASE_ROOT
delete = git_words.delete
move = git_words.move
rebase = git_words.rebase
reset = git_words.reset

NESTING = 4  # how deep an `sh -c` inside an `sh -c` is followed
TREES = (".code-factory", "worktrees")


class Rewrite(git_words.Value):
    """One rewriting git command found in a shell command: where it runs and what it is."""

    __slots__ = ("action", "command", "dir")

    def __init__(self, dir: str, action: Action, command: str) -> None:  # noqa: A002
        self.dir = dir
        self.action = action
        self.command = command

    def revision(self) -> str | None:
        """The commit whose relation to the pushed tip decides a rebase or a reset."""
        if self.action.kind in ("reset", "rebase") and isinstance(self.action.value, str):
            return self.action.value
        return None


class BranchState(git_words.Value):
    """What origin holds of the branch a command runs on, read by the caller.

    `head_pushed`: HEAD is an ancestor of, or equal to, `origin/<branch>`. `keeps_pushed`:
    `origin/<branch>` is an ancestor of the revision the command names; `None` when it names none
    or git cannot find it.
    """

    __slots__ = ("branch", "head_pushed", "keeps_pushed")

    def __init__(self, branch: str, *, head_pushed: bool, keeps_pushed: bool | None) -> None:
        self.branch = branch
        self.head_pushed = head_pushed
        self.keeps_pushed = keeps_pushed


def refusal(rewrite: Rewrite, state: BranchState | None) -> str | None:
    """Why `rewrite` is refused on a branch in `state` (`None`: origin has no such branch).

    A forced push is refused whatever origin holds; the rest only for the branch `state` describes.
    """
    command = rewrite.command
    if rewrite.action == FORCE:
        return (
            f"code-factory: refused `{command}`: the board pushes this branch and a forced push "
            "can replace a commit it has pushed. Add a new commit instead."
        )
    if state is None or not _leaves_pushed(rewrite.action, state):
        return None
    if rewrite.action.kind in ("delete", "move"):
        return (
            f"code-factory: refused `{command}`: the board has pushed this branch to "
            f"origin/{state.branch} and this command deletes or moves it. "
            "Add a new commit instead."
        )
    return (
        f"code-factory: refused `{command}`: the board has pushed this commit to "
        f"origin/{state.branch}. Add a new commit instead of rewriting it."
    )


def _leaves_pushed(action: Action, state: BranchState) -> bool:
    kind, value = action.kind, action.value
    if kind == "amend":
        return state.head_pushed
    if kind in ("rebase_root", "pull_rebase"):
        return True
    if kind == "rebase":
        return value is not None and state.keeps_pushed is False
    if kind == "reset":
        return state.keeps_pushed is False
    if kind == "delete":
        return state.branch in (value or ())
    return kind == "move" and value in (state.branch, "HEAD")


def in_ticket_tree(path: str) -> bool:
    """Whether `path` is, or is under, `<checkout>/.code-factory/worktrees/<name>`.

    By path components, not by substring.
    """
    parts = [part for part in path.split("/") if part and part != "."]
    # A tree is a folder below `worktrees`, so the pair cannot be the last two components.
    return any((parts[i], parts[i + 1]) == TREES for i in range(len(parts) - 2))


def rewrites(command: str, cwd: str) -> list[Rewrite]:
    """The rewriting git commands in a shell command run from `cwd`, in order."""
    found: list[Rewrite] = []
    _scan(command, cwd, 0, found)
    return found


def _scan(text: str, directory: str, depth: int, found: list[Rewrite]) -> None:
    for segment in shell.segments(text):
        words = shell.program_words(segment)
        if not words:
            continue
        name = words[0].rsplit("/", 1)[-1]
        if name == "cd":
            if len(words) > 1:
                directory = shell.resolve(directory, words[1])
        elif name == "git":
            rewrite = _git_rewrite(words, directory)
            if rewrite is not None:
                found.append(rewrite)
        elif (
            name in shell.SHELLS
            and depth < NESTING
            and (script := shell.shell_script(words)) is not None
        ):
            _scan(script, directory, depth + 1, found)


def _git_rewrite(words: list[str], directory: str) -> Rewrite | None:
    """The rewrite a `git ...` command makes, if any, and the directory it runs in."""
    at, config_rebases = 1, False
    while at < len(words) and words[at].startswith("-"):
        word = words[at]
        following = words[at + 1] if at + 1 < len(words) else None
        if word in ("-c", "--config-env"):
            config_rebases |= following is not None and git_words.rebase_setting(
                following, literal=word == "-c"
            )
        elif word.startswith("--config-env="):
            config_rebases |= git_words.rebase_setting(
                word.removeprefix("--config-env="), literal=False
            )
        if word == "-C":
            if following is None:
                return None
            directory = shell.resolve(directory, following)
            at += 1
        elif word in git_words.GIT_VALUED:
            at += 1
        at += 1
    if at >= len(words):
        return None
    rest = words[at + 1 :]
    action = git_words.git_action(words[at], rest, config_rebases=config_rebases)
    return None if action is None else Rewrite(directory, action, " ".join(words))
