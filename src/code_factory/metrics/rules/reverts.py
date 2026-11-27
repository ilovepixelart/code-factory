"""Which merges of the first-parent line a later change reverted."""

import re

from code_factory.metrics.rules.merges import Commit, first_parent_line, read_log

SHORTEST_ID = 7
_THIS_REVERTS = re.compile(r"This reverts commit ([0-9a-fA-F]+)")
_REVERT_MERGE = re.compile(r"Revert merge ([0-9a-fA-F]+)")
# A word starting with r or R, not preceded by a letter or digit: `unreverts #9` and `step#12`
# are no revert of a pull request, `Reverts o/repo#7` and `reverts #7` are.
_REVERTS_PULL = re.compile(r"(?<![A-Za-z0-9])[rR]everts +([^\s#]*)#(\d+)", re.ASCII)


def _brought_in(commits: dict[str, Commit], line: list[str]) -> dict[str, str]:
    """For each commit, the first-parent commit that brought it in (the line, oldest first)."""
    by: dict[str, str] = {}
    for landed in reversed(line):
        stack = [landed]
        while stack:
            sha = stack.pop()
            if sha in by:
                continue
            by[sha] = landed
            stack.extend(p for p in commits[sha].parents if p not in by and p in commits)
    return by


def _named_ids(message: str) -> list[str]:
    subject = message.split("\n", 1)[0]
    found = _THIS_REVERTS.findall(message) + _REVERT_MERGE.findall(subject)
    return [sha for sha in found if len(sha) >= SHORTEST_ID]


def _named_pulls(message: str) -> list[str]:
    return [
        number
        for repository, number in _REVERTS_PULL.findall(message)
        if not repository or "/" in repository
    ]


def _merge_of(commits: dict[str, Commit], line: list[str], number: str) -> str | None:
    prefix = f"Merge pull request #{number} "
    return next((sha for sha in line if commits[sha].message.startswith(prefix)), None)


def _after(line: list[str], landing: str | None, merge: str) -> bool:
    """Whether the change at `landing` came after `merge` on the line (an unplaced one counts)."""
    return landing is None or line.index(landing) < line.index(merge)


def reverted_commits(log: str) -> set[str]:
    """The commits of the first-parent line that a commit outside their own change says it reverts.

    By `This reverts commit <id>` anywhere, `Revert merge <id>` in the subject (ids of at least
    seven hex digits; a prefix matching two commits names none), or `reverts #<n>` and
    `Reverts <owner>/<repo>#<n>`. A change is the first-parent commit that brought a commit in: a
    revert inside the change of its own target does not count.
    """
    order, commits = read_log(log)
    line = first_parent_line(order, commits)
    by = _brought_in(commits, line)
    reverted: set[str] = set()
    for sha, commit in commits.items():
        landed: list[str] = []
        for prefix in _named_ids(commit.message):
            matches = [c for c in commits if c.startswith(prefix)]
            if len(matches) == 1 and matches[0] in by:
                landed.append(by[matches[0]])
        for number in _named_pulls(commit.message):
            merge = _merge_of(commits, line, number)
            if merge is not None and _after(line, by.get(sha), merge):
                landed.append(merge)
        reverted.update(target for target in landed if by.get(sha) != target)
    return reverted
