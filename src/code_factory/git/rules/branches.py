"""Names: branches, ticket trees, wip refs."""

import re

_HEX = re.compile(r"[0-9a-f]+", re.IGNORECASE)
_PREFIXES = ("origin/", "remotes/", "refs/", "heads/", "tags/")
_HELD = " ~^:?*[\\"
_PLAIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_PSEUDO = re.compile(r"[A-Z0-9_]*HEAD")
LEFT_OUT = (
    ":(exclude,glob)**/.env",
    ":(exclude,glob)**/.env.*",
    ":(exclude,glob)**/*.pem",
    ":(exclude,glob)**/*.key",
)


def is_commit_id(text: str) -> bool:
    """Whether `text` spells a full commit id (40 or 64 hex digits)."""
    return len(text) in {40, 64} and _HEX.fullmatch(text) is not None


def _held_character(name: str) -> str | None:
    for char in name:
        if ord(char) < 32 or ord(char) == 127:  # noqa: PLR2004  # DEL
            return "a control character"
        if char in _HELD:
            return "a space" if char == " " else char
    return None


def _other_ref(name: str) -> str:
    lower = name.lower()
    return next((prefix for prefix in _PREFIXES if lower.startswith(prefix)), "")


def branch_refusal(name: str) -> str | None:  # one flat rule list, in git's order
    """Why `name` is not a plain branch name, the first rule it breaks; `None` when it is one.

    Git's own rules (`git check-ref-format --branch`) plus what the board must never pass as a
    revision: `@`, a full commit id, a top-level pseudo ref, another ref's prefix (also in another
    case, for a case-folding file system), a leading `-` and any non-ASCII character.
    """
    held = _held_character(name)
    other = _other_ref(name)
    parts = name.split("/")
    pseudo = _PSEUDO.fullmatch(name) is not None and name != "HEAD"
    rules = (
        (
            not name.isascii(),
            (
                "it holds a non-ASCII character, which a case-folding file system can read as "
                "another ref"
            ),
        ),
        (
            pseudo,
            "it looks like a top-level ref such as FETCH_HEAD, which git reads as that ref",
        ),
        (bool(other), f"it starts with {other}, which git reads as another ref"),
        (name.startswith("-"), "it starts with -, which git reads as an option"),
        (name in {"HEAD", "@"}, f"{name} is git's name for the checked-out commit"),
        (is_commit_id(name), "it is a full commit id, which git reads as that commit"),
        (held is not None, f"it holds {held}, which git refuses in a branch name"),
        (".." in name, "it holds .., which git reads as a range"),
        ("@{" in name, "it holds @{, which git reads as a reflog or upstream expression"),
        (name.startswith("/"), "it starts with /"),
        (name.endswith("/"), "it ends with /"),
        ("//" in name, "it holds //"),
        (name.endswith("."), "it ends with ."),
        (any(part.startswith(".") for part in parts), "a part of it starts with ."),
        (any(part.endswith(".lock") for part in parts), "a part of it ends with .lock"),
    )
    return next((why for broken, why in rules if broken), None)


def is_plain_segment(ticket_id: str) -> bool:
    """Whether `ticket_id` is one plain path segment, which is also safe inside `refs/wip/<id>`.

    Letters, digits, `-` and `_` only, starting with a letter or digit.
    """
    return _PLAIN.fullmatch(ticket_id) is not None


def wip_ref(ticket_id: str) -> str:
    """The ref a ticket's unfinished work is saved in."""
    return f"refs/wip/{ticket_id}"


def branch_for(ticket_id: str) -> str:
    """The branch a ticket gets: `CF-12` works on `ticket/cf-12`."""
    return f"ticket/{ticket_id.lower()}"


def attempt_tree_name(ticket_id: str, attempt: int) -> str:
    """The folder of attempt `attempt`; none (0) is the ticket's own."""
    return ticket_id if attempt == 0 else f"{ticket_id}-{attempt}"


def attempt_branch(branch: str, attempt: int) -> str:
    """The branch attempt `attempt` works on; none (0) is the ticket's own."""
    return branch if attempt == 0 else f"{branch}-attempt-{attempt}"
