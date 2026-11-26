"""Pure release rules: versions, tags, the ids a text names, and the notes a draft starts from."""

import re
from collections.abc import Iterable, Sequence

from code_factory.platform.errors import BadRequestError
from code_factory.releases.models import ReleaseState, ReleaseTicket

# Three decimal numbers of up to nine digits and nothing else: git's version sort puts
# `1.2.0-rc.1` after `1.2.0`, so the newest tag could name a pre-release, and a longer number
# would not fit an index entry or `int()`'s digit limit. `[0-9]` and `fullmatch`: `\d` takes
# other scripts' digits and `$` lets a newline through.
_VERSION = re.compile(r"[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}")
# A full SHA-1 or SHA-256 object name, as the table's `tag_commit` check holds it.
_COMMIT = re.compile(r"[0-9a-f]{40}([0-9a-f]{24})?")
NOTES_LIMIT = 100_000
_TAG_PREFIX = "refs/tags/"
_PEELED = "^{}"

NOTHING_MERGED = "Nothing merged since the last release."
# Section headings in order, each with the ticket types it lists in order.
SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Added", ("feature",)),
    ("Changed", ("upgrade", "refactor", "docs")),
    ("Fixed", ("bug", "hotfix")),
)


def is_version(text: str) -> bool:
    """Whether `text` is `MAJOR.MINOR.PATCH` of decimal numbers."""
    return _VERSION.fullmatch(text) is not None


def version_key(version: str) -> tuple[int, int, int]:
    """The three numbers of a version, for ordering (`0.10.0` above `0.9.0`)."""
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def listed_tags(ls_remote: str) -> list[tuple[str, str]]:
    """Each tag `git ls-remote --tags` printed, with the object it names.

    An annotated tag names its tag object; the `^{}` line that peels it to a commit is skipped.
    """
    tags: list[tuple[str, str]] = []
    for line in ls_remote.splitlines():
        obj, separator, reference = line.partition("\t")
        name = reference.removeprefix(_TAG_PREFIX)
        if separator and name != reference and not name.endswith(_PEELED):
            tags.append((name, obj))
    return tags


def newest_release(names: Iterable[str]) -> str | None:
    """The highest release tag `v<MAJOR.MINOR.PATCH>` of `names`, by its numbers."""
    versions = [
        (version_key(version), name)
        for name in names
        if name.startswith("v") and is_version(version := name[1:])
    ]
    return max(versions)[1] if versions else None


def ticket_ids_in(notes: str, prefix: str) -> list[str]:
    """The ticket ids `notes` names, in order of first appearance, none twice.

    An id counts when no word character or `-` comes before it, no digit follows it, and it has
    at most 18 digits (a number the store can issue). `CF-1` is in `see CF-1.`, not in `CF-12`,
    `XCF-1` or `a-CF-1`.
    """
    pattern = re.compile(rf"(?<![\w-]){re.escape(prefix)}-[0-9]{{1,18}}(?![0-9])")
    return list(dict.fromkeys(pattern.findall(notes)))


def release_notes(version: str, tickets: Sequence[ReleaseTicket]) -> str:
    """The notes a draft starts from: a section per kind of change, a line per ticket.

    Inside a section the types keep the order of `SECTIONS` and the tickets of a type the order
    given; a ticket of any other type is left out.
    """
    lines = [f"# {version}", ""]
    for heading, kinds in SECTIONS:
        chosen = [
            f"- {ticket.id}: {ticket.title}"
            for kind in kinds
            for ticket in tickets
            if ticket.kind == kind
        ]
        if chosen:
            lines += [f"## {heading}", *chosen, ""]
    if len(lines) == 2:  # noqa: PLR2004  # the heading and its blank line: no section was added
        lines += [NOTHING_MERGED, ""]
    return "\n".join(lines)


def check_version(version: str) -> str:
    """`version` itself, or the refusal that names the form."""
    if not is_version(version):
        msg = f"{version!r} is not a version MAJOR.MINOR.PATCH: three decimal numbers, as 1.4.0"
        raise BadRequestError(msg)
    return version


def check_notes(notes: str) -> str:
    """`notes` itself, or the refusal for text over `NOTES_LIMIT` characters."""
    if len(notes) > NOTES_LIMIT:
        msg = f"the notes are {len(notes)} characters; the limit is {NOTES_LIMIT}"
        raise BadRequestError(msg)
    return notes


def check_commit(commit: str) -> str:
    """`commit` itself, or the refusal for anything but a full lower case object name."""
    if _COMMIT.fullmatch(commit) is None:
        msg = f"{commit!r} is not a full commit hash: 40 hexadecimal digits in lower case"
        raise BadRequestError(msg)
    return commit


def state_of(published: object | None, tagged: object | None) -> ReleaseState:
    """The state a release's `published_at` and `tagged_at` put it in."""
    if tagged is not None:
        return ReleaseState.TAGGED
    return ReleaseState.DRAFT if published is None else ReleaseState.PUBLISHED


def ticket_order(ticket_id: str) -> tuple[str, int]:
    """Sort key for `CF-12` style ids: by prefix, then by number (`CF-9` before `CF-10`)."""
    prefix, _, number = ticket_id.rpartition("-")
    return prefix, int(number)
