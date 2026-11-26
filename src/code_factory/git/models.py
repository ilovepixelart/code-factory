"""What the git service takes and answers, and the errors it raises.

Everything here is data: the rules in `rules/` read these values, the adapters fill them, and no
other module sees a type of this module's layers below the service.
"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from code_factory.platform.errors import ConflictError

FETCH_NOT_A_COMMIT = (
    "its run's branch is not a commit the board can take, so the board brought nothing back"
)
FETCH_NOT_FORWARD = (
    "its run's branch does not build on the branch the board holds, so the board brought "
    "nothing back"
)
FETCH_NOT_MOVED = (
    "git did not move its branch in the main repository, so the board brought nothing back"
)
FETCH_CHECKED_OUT = (
    "its branch is checked out in the main repository, so the board brought nothing back; "
    "check out another branch there"
)
DIFF_LIMIT = 400
MERGE_LOG_LIMIT = 1000


class TreeRedirectedError(ConflictError):
    """A board tree's git folder is not the one the board made, so no git was run in it."""


class FetchRefusedError(ConflictError):
    """The board brought nothing back from a clone; the sentence says why."""


class Frozen(BaseModel):
    """Values are compared and shared, never edited."""

    model_config = ConfigDict(frozen=True)


class RefTips(Frozen):
    """The branches of a repository: local names, `origin/` names and each one's tip."""

    local: frozenset[str] = frozenset()
    remote: frozenset[str] = frozenset()
    tips: dict[str, str] = Field(default_factory=dict)


class GitFacts(Frozen):
    """The branches, their tips, the merges and the log of the default branch.

    `known` is false when any read failed: nothing then reads as merged. `main_line` holds the
    commits of the default branch's first-parent line; a branch whose tip is one of them holds
    no commit of its own. `main_subjects` contains the subjects available in the recent log for
    those first-parent commits.
    """

    default_branch: str
    local: frozenset[str]
    remote: frozenset[str]
    tips: dict[str, str]
    merged_in: frozenset[str]
    log: str
    merged_heads: frozenset[str] = frozenset()
    main_line: frozenset[str] = frozenset()
    main_subjects: dict[str, str] = Field(default_factory=dict)
    known: bool = True


class BranchState(Frozen):
    """What git says of one ticket branch."""

    tip: str
    remote_tip: str
    ahead: int
    merged: bool
    pushed: bool


class Line(Frozen):
    """One line of a change: added, removed or kept, with its number in the new file."""

    kind: str
    number: int | None
    text: str


class FileChange(Frozen):
    """One changed file and its lines; an empty path for a removed file."""

    path: str
    lines: list[Line]


class Changes(Frozen):
    """A diff's files, and whether it was cut at the limit."""

    files: list[FileChange]
    cut: bool


class ChangesView(Changes):
    """What the ticket page shows of a branch."""

    limit: int = DIFF_LIMIT
    branch: str = ""
    default_branch: str = ""


class Merge(Frozen):
    """One pull request merged into the default branch."""

    commit: str
    head: str
    pull: int | None
    branch: str
    ticket: str | None
    at: float
    started: float


class LogEntry(Frozen):
    """A commit with its whole message, as the metrics module reads the log."""

    commit: str
    parents: list[str]
    at: float
    message: str


class MergeCheck(Frozen):
    """What `merge-tree` said of two commits: clean, or the files that conflict."""

    clean: bool
    files: list[str] = Field(default_factory=list)


class TreeKind(StrEnum):
    """What a board-made place is."""

    WORKTREE = "worktree"
    CLONE = "clone"


class TreeRecord(Frozen):
    """The trust record of a board-made place (a `git_trees` row)."""

    repository: str
    name: str
    kind: TreeKind
    ticket_id: str
    attempt: int
    branch: str
    path: str
    token: str


class TreeInfo(Frozen):
    """A tree as `list_trees` and `start_worktree` answer it."""

    name: str
    kind: TreeKind
    ticket_id: str
    branch: str
    path: str
    ahead: int | None = None
    uncommitted: int = 0
    merged: bool = False
    valid: bool = True
    orphan: str = ""
    made: bool = False  # `start_worktree` made it in this call, not found it


class FolderSnapshot(Frozen):
    """What an adapter read of a tree's git folders, for `validate_tree` to judge.

    A text is `None` when it could not be read; a `*_resolved` path is after following every link
    (a path that does not exist resolves to itself).
    """

    resolved_path: str
    nested_git: bool = False
    dot_git_kind: str = "missing"  # "file", "dir", "link" or "missing"
    dot_git_resolved: str = ""
    dot_git_text: str | None = None
    admin_resolved: str = ""
    gitdir_text: str | None = None
    commondir_text: str | None = None
    commondir_exists: bool = False
    common_dir: str = ""
    info_resolved: str = ""
    alternates_resolved: str = ""
    alternates_text: str | None = None
    alternates_exists: bool = False
    token_text: str | None = None


class TreeFolders(Frozen):
    """The git folders of a valid tree."""

    worktree: str
    admin: str
    common: str
    is_clone: bool


class Redirected(Frozen):
    """A tree that does not validate, and the sentence for the person."""

    reason: str


class StackBase(Frozen):
    """Where a stacked ticket's branch is cut from and whether origin holds the parent."""

    cut: str
    on_origin: bool


class Removed(Frozen):
    """What `remove_worktree` removed."""

    branch: str
    branch_deleted: bool


class Saved(Frozen):
    """A ticket's unfinished work kept in `refs/wip/<id>` and the refs now on origin."""

    commit: str
    sent: list[str] = Field(default_factory=list)
    not_sent: str = ""


class CatchUp(Frozen):
    """Whether the main checkout moved to origin's default branch; `reason` when it did not."""

    moved: bool
    reason: str = ""


class Merged(Frozen):
    """The branch was merged; `url` is the pull request."""

    url: str


class NotMerged(Frozen):
    """The branch was pushed and left open; `why` says what it waits for."""

    why: str


class Refused(Frozen):
    """The land was refused before anything was pushed."""

    why: str


class Conflicted(Frozen):
    """Merging the default branch in conflicts in these files; nothing was written."""

    files: list[str]


Landed = Merged | NotMerged | Refused | Conflicted


class Updated(Frozen):
    """A ticket branch took the default branch's tip."""

    tip: str


class Current(Frozen):
    """The branch already holds the default branch's tip."""


Updating = Updated | Current | Conflicted | Refused


class TicketRef(Frozen):
    """What git needs to know of a ticket."""

    id: str
    title: str
    kind: str
    labels: list[str]
    branch: str
    blocker_ids: list[str]


class PullRef(Frozen):
    """A pull request the forge opened."""

    number: int
    url: str


class HookOutcome(Frozen):
    """The setup command's result: its exit code (`None` when it ran out of time) and log."""

    code: int | None
    log: Path | None = None
