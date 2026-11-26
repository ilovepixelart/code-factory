"""Merged pull requests of the default branch, merge-tree answers and path patterns."""

import re
from fnmatch import fnmatchcase

from code_factory.git.models import LogEntry, Merge

FILING = "tickets/"
WALK_LIMIT = 10_000
_TICKET = re.compile(r"([A-Za-z]+)-([0-9]+)")
_PULL = re.compile(r"Merge pull request #(.*?) from (.*)")


def merged_from(subject: str) -> tuple[int | None, str] | None:
    """The pull request number and branch GitHub's merge subject names.

    `Merge pull request #7 from owner/ticket/cf-12` is `(7, "ticket/cf-12")`.
    """
    found = _PULL.fullmatch(subject)
    if found is None:
        return None
    number, source = str(found.group(1)), str(found.group(2))
    branch = source.partition("/")[2] if "/" in source else source
    pull: int | None = int(number) if number.isdigit() else None
    return pull, branch.strip()


def ticket_of(branch: str) -> str | None:
    """The ticket a branch names in its last part: `ticket/cf-12` is `CF-12`."""
    last = branch.rsplit("/", 1)[-1]
    found = _TICKET.match(last)
    return f"{found[1].upper()}-{found[2]}" if found else None


def _commits(log: str) -> tuple[list[str], dict[str, tuple[list[str], float, str]]]:
    order: list[str] = []
    commits: dict[str, tuple[list[str], float, str]] = {}
    for line in log.splitlines():
        fields = line.split("\t", 3)
        if len(fields) < 3:  # noqa: PLR2004  # hash, parents, time
            continue
        try:
            at = float(fields[2])
        except ValueError:
            continue
        order.append(fields[0])
        commits[fields[0]] = (fields[1].split(), at, fields[3] if len(fields) > 3 else "")  # noqa: PLR2004
    return order, commits


def _first_own_commit(
    tip: str, line: set[str], commits: dict[str, tuple[list[str], float, str]]
) -> float | None:
    seen: set[str] = set()
    waiting = [tip]
    oldest: float | None = None
    while waiting:
        commit = waiting.pop()
        if commit in line or commit in seen:
            continue
        seen.add(commit)
        if len(seen) > WALK_LIMIT:
            continue
        if commit not in commits:
            continue
        parents, at, _ = commits[commit]
        oldest = at if oldest is None else min(oldest, at)
        waiting.extend(parents)
    return oldest


def parse_merges(log: str, since: float) -> list[Merge]:
    r"""The pull requests merged into the default branch at or after `since`, newest first.

    `log` is `%H\\t%P\\t%ct\\t%s` of the default branch, newest first. Only merges on its
    first-parent line count; a branch that only files tickets ships no work. `started` is the
    oldest commit reachable from the head before the main line, the walk capped at 10,000.
    """
    order, commits = _commits(log)
    line: list[str] = []
    at = order[0] if order else None
    while at is not None and at in commits and at not in line:
        line.append(at)
        parents = commits[at][0]
        at = parents[0] if parents else None
    on_line = set(line)
    merges: list[Merge] = []
    for commit in line:
        parents, when, subject = commits[commit]
        source = merged_from(subject)
        if len(parents) < 2 or when < since or source is None:  # noqa: PLR2004  # a merge
            continue
        pull, branch = source
        if branch.startswith(FILING):
            continue
        started = _first_own_commit(parents[1], on_line, commits)
        merges.append(
            Merge(
                commit=commit,
                head=parents[1],
                pull=pull,
                branch=branch,
                ticket=ticket_of(branch),
                at=when,
                started=when if started is None else started,
            )
        )
    return merges


def parse_log_entries(text: str) -> list[LogEntry]:
    """Read `%H%x1f%P%x1f%ct%x1f%B%x1e` records."""
    entries = []
    for record in text.split("\x1e"):
        fields = record.strip("\n").split("\x1f", 3)
        if len(fields) != 4:  # noqa: PLR2004  # hash, parents, time, message
            continue
        try:
            at = float(fields[2])
        except ValueError:
            continue
        entries.append(
            LogEntry(commit=fields[0], parents=fields[1].split(), at=at, message=fields[3])
        )
    return entries


def read_merge_tree(code: int | None, stdout: str) -> list[str] | None:
    """The conflicted files `git merge-tree --write-tree --name-only` named; `[]` when clean.

    `None` when it did not merge: git exits 1 for a name it cannot read as well as for a
    conflict, and only a merge prints its tree id on the first line.
    """
    lines = stdout.splitlines()
    if not lines or not lines[0]:
        return None
    if code == 0:
        return []
    if code == 1:
        return [line for line in lines[1:] if line]
    return None


def pair_key(first: str, second: str) -> str:
    """The one key of a pair of commits, whichever is named first."""
    low, high = sorted((first, second))
    return f"{low}..{high}"


def path_matches(path: str, pattern: str) -> bool:
    """Whether `path` matches `pattern`: `**` is any number of folders, `*?[]` within one name."""
    return _match([part for part in path.split("/") if part], [p for p in pattern.split("/") if p])


def _match(names: list[str], parts: list[str]) -> bool:
    if not parts:
        return not names
    head, rest = parts[0], parts[1:]
    if head == "**":
        return any(_match(names[skip:], rest) for skip in range(len(names) + 1))
    return bool(names) and fnmatchcase(names[0], head) and _match(names[1:], rest)


def clash(on_branch: list[str], on_main: list[str], globs: list[str]) -> str | None:
    """Why a branch and main are checked together: the first glob a file of each side matches."""
    for glob in globs:
        ours = next((path for path in on_branch if path_matches(path, glob)), None)
        theirs = next((path for path in on_main if path_matches(path, glob)), None)
        if ours is not None and theirs is not None:
            return f"{ours} on the branch and {theirs} on main match {glob}"
    return None
