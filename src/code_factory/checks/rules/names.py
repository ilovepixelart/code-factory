"""How a check's log, cache and time limit are named."""

import hashlib
import re
from datetime import timedelta

DEFAULT_LIMIT = timedelta(seconds=3600)
_OUTSIDE_A_NAME = re.compile(r"[^A-Za-z0-9_-]")
_SECOND = re.compile(r"[0-9]+")
_ANY_LOG = re.compile(r"[^/]+-(?:main|[A-Z][A-Z0-9]*-[0-9]+)-[0-9]+\.log")


def checks_limit(configured: int | None) -> timedelta | None:
    """How long a run may take: an hour unset, no limit at 0, else `configured` seconds."""
    if configured is None:
        return DEFAULT_LIMIT
    return timedelta(seconds=configured) if configured > 0 else None


def cache_key(ticket_id: str) -> str:
    """The folder name of a ticket's cache: anything but letters, digits, `-` and `_` is `_`."""
    return _OUTSIDE_A_NAME.sub("_", ticket_id)


def log_name(repository: str, subject: str, second: int) -> str:
    """`<repository>-<subject>-<second>.log`."""
    return f"{repository}-{subject}-{second}.log"


def log_name_ok(name: str, repository: str, subject: str) -> bool:
    """Whether `name` is a log of `subject` in `repository`: that prefix, digits, `.log`."""
    prefix = f"{repository}-{subject}-"
    if not name.startswith(prefix) or not name.endswith(".log"):
        return False
    return _SECOND.fullmatch(name[len(prefix) : -len(".log")]) is not None


def log_name_any(name: str) -> bool:
    """Whether `name` is a log of some ticket or of main: `<repository>-<subject>-<second>.log`."""
    return "/" not in name and not name.startswith(".") and _ANY_LOG.fullmatch(name) is not None


def tree_name(head: str, status: str = "", changes: str = "") -> str:
    """The name of a tree's state: a digest of its commit, its status and its changes.

    A tree with no status and no changes, such as a runner's clean checkout, is named by `head`.
    """
    return hashlib.sha256(f"{head}\x00{status}\x00{changes}".encode()).hexdigest()[:40]
