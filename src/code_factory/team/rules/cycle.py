"""Where this cycle starts, each ticket's first commit, and the ticket a subagent works on."""

import re
from collections.abc import Iterable, Sequence

from code_factory.team.models import Cycle

CYCLE_SECONDS = 604_800.0
_TICKET = re.compile(r"[A-Z]+-[0-9]+")
_RELEASE_TAG = re.compile(r"v[0-9]")
_WORKTREE_NAME = re.compile(r"[A-Za-z0-9_-]+")


def subagent_ticket(calls: Iterable[str], marker: str) -> str | None:
    """The ticket whose worktree the newest tool call names, given newest first.

    `marker` is the folder every worktree lives in, from configuration.
    """
    for call in calls:
        _before, found, after = call.partition(marker)
        name = _WORKTREE_NAME.match(after) if found else None
        if name:
            return name.group()
    return None


def first_commits(log: str) -> dict[str, float]:
    """Each ticket's earliest commit from `%at<TAB>%s` lines whose subject starts `<ID>:`."""
    first: dict[str, float] = {}
    for line in log.splitlines():
        stamp, tab, subject = line.partition("\t")
        ticket, colon, _rest = subject.partition(":")
        if not (tab and colon and _TICKET.fullmatch(ticket)):
            continue
        try:
            at = float(stamp.strip())
        except ValueError:
            continue
        first[ticket] = min(at, first.get(ticket, at))
    return first


def cycle_since(now: float, tags: Sequence[tuple[str, float]]) -> Cycle:
    """Where this cycle starts: the newest release tag not after `now`, else seven days back."""
    releases = [tag for tag in tags if _RELEASE_TAG.match(tag[0]) and tag[1] <= now]
    if not releases:
        return Cycle(since=now - CYCLE_SECONDS, from_="the last 7 days")
    name, at = max(releases, key=lambda tag: tag[1])
    return Cycle(since=at, from_=f"since {name}")
