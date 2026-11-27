"""Merged pull requests read from a `git log`, and what the checks and the commits say of them.

The log is `git log --format=%H%x1f%P%x1f%ct%x1f%B%x1e`: one record per commit, newest first.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from code_factory.metrics.models import Autonomy, CheckRecord, ChecksVerdict, Merge

FIELD = "\x1f"
RECORD = "\x1e"
LOG_FORMAT = "--format=%H%x1f%P%x1f%ct%x1f%B%x1e"
WALK_LIMIT = 10_000
FILING = "tickets/"  # a branch that only files tickets ships no work
_SUBJECT = re.compile(r"Merge pull request #(?P<pull>[^ ]*) from (?P<from>.+)")
_TICKET = re.compile(r"(?P<prefix>[A-Za-z]+)-(?P<digits>\d+)", re.ASCII)


@dataclass(frozen=True)
class Commit:
    """One commit of a log."""

    parents: tuple[str, ...]
    at: float
    message: str

    @property
    def subject(self) -> str:
        """The first line of the message."""
        return self.message.split("\n", 1)[0]


def read_log(log: str) -> tuple[list[str], dict[str, Commit]]:
    """The commit ids in log order and each commit by id; a malformed record is skipped."""
    order: list[str] = []
    commits: dict[str, Commit] = {}
    for chunk in log.split(RECORD):
        fields = chunk.lstrip("\n").split(FIELD, 3)
        if len(fields) != 4 or not fields[0]:  # noqa: PLR2004  # id, parents, time, message
            continue
        try:
            at = float(fields[2].strip())
        except ValueError:
            continue
        order.append(fields[0])
        commits[fields[0]] = Commit(tuple(fields[1].split()), at, fields[3])
    return order, commits


def first_parent_line(order: Sequence[str], commits: dict[str, Commit]) -> list[str]:
    """The first-parent line from the newest commit, newest first."""
    line: list[str] = []
    seen: set[str] = set()
    at = order[0] if order else None
    while at is not None and at in commits and at not in seen:
        line.append(at)
        seen.add(at)
        parents = commits[at].parents
        at = parents[0] if parents else None
    return line


def ticket_of(branch: str) -> str | None:
    """The ticket the last part of a branch names: `ticket/cf-12` and `cf-12-code` are `CF-12`."""
    found = _TICKET.match(branch.rsplit("/", 1)[-1])
    return f"{found['prefix'].upper()}-{found['digits']}" if found else None


def github_web(remote: str) -> str | None:
    """The repository's address on GitHub from an ssh or https remote, `.git` stripped."""
    remote = remote.strip()
    for prefix in ("git@github.com:", "https://github.com/", "ssh://git@github.com/"):
        if remote.startswith(prefix):
            name = remote.removeprefix(prefix).removesuffix(".git")
            return f"https://github.com/{name}" if name else None
    return None


def _merged_from(subject: str) -> tuple[int | None, str] | None:
    found = _SUBJECT.fullmatch(subject)
    if not found:
        return None
    pull = str(found["pull"])
    source = str(found["from"])
    branch = source.split("/", 1)[1] if "/" in source else source
    return (int(pull) if pull.isascii() and pull.isdigit() else None), branch.strip()


def _first_own_commit(tip: str, line: set[str], commits: dict[str, Commit]) -> float | None:
    """The time of the oldest commit reachable from `tip` before the first-parent line."""
    seen: set[str] = set()
    waiting = [tip]
    oldest: float | None = None
    while waiting:
        sha = waiting.pop()
        if sha in line or sha in seen:
            continue
        seen.add(sha)
        if len(seen) > WALK_LIMIT or sha not in commits:
            continue
        commit = commits[sha]
        oldest = commit.at if oldest is None else min(oldest, commit.at)
        waiting.extend(commit.parents)
    return oldest


def parse_merges(log: str, since: float) -> list[Merge]:
    """The pull requests merged into the log's first-parent line at or after `since`, newest first.

    A merge is a first-parent commit with two or more parents whose subject is GitHub's merge
    subject. A branch under `tickets/` is left out. `started` is the oldest commit the branch
    brought that the line did not hold (the walk reads at most 10000 commits), else the merge time.
    """
    order, commits = read_log(log)
    line = first_parent_line(order, commits)
    line_set = set(line)
    merges: list[Merge] = []
    for sha in line:
        commit = commits[sha]
        parsed = _merged_from(commit.subject) if len(commit.parents) >= 2 else None  # noqa: PLR2004
        if parsed is None or commit.at < since or parsed[1].startswith(FILING):
            continue
        pull, branch = parsed
        started = _first_own_commit(commit.parents[1], line_set, commits)
        merges.append(
            Merge(
                commit=sha,
                head=commit.parents[1],
                pull=pull,
                branch=branch,
                ticket=ticket_of(branch),
                at=commit.at,
                started=commit.at if started is None else started,
            )
        )
    return merges


def autonomy_class(rev_list: str | None, made: set[str], *, recorded: bool) -> Autonomy:
    """How a merge was built, from `rev-list --parents commit^1..commit^2` and the runs' commits.

    Unknown when no run recorded its commits or git could not read the range. A commit counts when
    it has fewer than two parents or a later parent inside the range (a merge of the default
    branch into the branch has none and is skipped); one a run did not make makes it assisted.
    """
    if not recorded or rev_list is None:
        return Autonomy.UNKNOWN
    rows = [line.split() for line in rev_list.splitlines() if line.strip()]
    in_range = {row[0] for row in rows}
    by_hand = any(
        row[0] not in made
        for row in rows
        if len(row) < 3 or any(parent in in_range for parent in row[2:])  # noqa: PLR2004
    )
    return Autonomy.ASSISTED if by_hand else Autonomy.AUTONOMOUS


def checks_verdict(records: Sequence[CheckRecord], head: str) -> ChecksVerdict:
    """What the newest record naming `head` says: exit code 0 passed, anything else failed."""
    if not head:
        return ChecksVerdict.NONE
    named = [r for r in records if r.commit == head]
    if not named:
        return ChecksVerdict.NONE
    newest = max(enumerate(named), key=lambda pair: (pair[1].at, pair[0]))[1]
    return ChecksVerdict.PASSED if newest.exit_code == 0 else ChecksVerdict.FAILED
