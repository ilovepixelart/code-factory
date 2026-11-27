"""Pure ticket rules: ids, the column a ticket's facts put it in, and what a field may hold."""

import re
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

from code_factory.platform.errors import BadRequestError
from code_factory.tickets.models import Column, PullRequestState, WrittenFields

PREFIX = "CF-"
MAX_NUMBER = 2**63 - 1  # the sequence's bigint: a larger number names no ticket


def ticket_id(number: int) -> str:
    """The id a person reads, `CF-<n>`."""
    return f"{PREFIX}{number}"


def ticket_number(text: str) -> int:
    """The number of an id `CF-<n>`; `BadRequestError` for anything else.

    A number above `MAX_NUMBER` is returned as one that is above it: it names no ticket.
    """
    digits = text.removeprefix(PREFIX)
    if digits == text or not (digits.isascii() and digits.isdigit()):
        number = 0
    else:  # a longer digit string than the column holds is beyond it without being parsed
        number = int(digits) if len(digits) <= len(str(MAX_NUMBER)) else MAX_NUMBER + 1
    if number == 0:
        msg = f"{text!r} is not a ticket id CF-<n>: write CF and a number from 1, as in CF-12"
        raise BadRequestError(msg)
    return number


def column_of(branch: str, pull_request: PullRequestState | None, merged: bool) -> Column:
    """The column a ticket's facts put it in.

    Merged once its work is merged (by hand or through its pull request), Review while its pull
    request is open, Build while it has a branch, Spec before that. The column is never stored.
    """
    if merged or pull_request is PullRequestState.MERGED:
        return Column.MERGED
    if pull_request is PullRequestState.OPEN:
        return Column.REVIEW
    if branch:
        return Column.BUILD
    return Column.SPEC


_REFS = ("origin/", "remotes/", "refs/", "heads/", "tags/")
_REFUSED_CHARACTERS = " ~^:?*[\\"
_COMMIT_ID_LENGTHS = (40, 64)
_NON_ASCII = (
    "it holds a non-ASCII character, which a case-folding file system can read as another ref"
)


def _held_character(name: str) -> str | None:
    for character in name:
        if character == " ":
            return "a space"
        if character.isascii() and not character.isprintable():
            return "a control character"
        if character in _REFUSED_CHARACTERS:
            return character
    return None


def _ref_like_refusal(name: str) -> str | None:
    lower = name.lower()
    prefix = next((p for p in _REFS if lower.startswith(p)), None)
    pseudo = name.endswith("HEAD") and all(c.isupper() or c.isdigit() or c == "_" for c in name)
    commit_id = len(name) in _COMMIT_ID_LENGTHS and all(c in "0123456789abcdefABCDEF" for c in name)
    rules = [
        (not name.isascii(), _NON_ASCII),
        (
            pseudo and name != "HEAD",
            "it looks like a top-level ref such as FETCH_HEAD, which git reads as that ref",
        ),
        (prefix is not None, f"it starts with {prefix}, which git reads as another ref"),
        (name.startswith("-"), "it starts with -, which git reads as an option"),
        (name in {"HEAD", "@"}, f"{name} is git's name for the checked-out commit"),
        (commit_id, "it is a full commit id, which git reads as that commit"),
    ]
    return next((why for broken, why in rules if broken), None)


def _shape_refusal(name: str) -> str | None:
    held = _held_character(name)
    parts = name.split("/")
    rules = [
        (held is not None, f"it holds {held}, which git refuses in a branch name"),
        (".." in name, "it holds .., which git reads as a range"),
        ("@{" in name, "it holds @{, which git reads as a reflog or upstream expression"),
        (name.startswith("/"), "it starts with /"),
        (name.endswith("/"), "it ends with /"),
        ("//" in name, "it holds //"),
        (name.endswith("."), "it ends with ."),
        (any(part.startswith(".") for part in parts), "a part of it starts with ."),
        (any(part.endswith(".lock") for part in parts), "a part of it ends with .lock"),
    ]
    return next((why for broken, why in rules if broken), None)


def branch_refusal(name: str) -> str | None:
    """Why `name` is not a plain branch name; `None` when it is.

    Beyond what `git check-ref-format --branch` refuses, a name git would read as another ref (a
    remote's, a tag's, a commit id, a top-level ref) is refused too.
    """
    return _ref_like_refusal(name) or _shape_refusal(name)


def check_branch(name: str) -> str:
    """`name` stripped when it is a plain branch name; `BadRequestError` naming why if not."""
    branch = name.strip()
    if not branch:
        raise BadRequestError("a branch needs a name; clear the branch to remove it")
    why = branch_refusal(branch)
    if why is not None:
        raise BadRequestError(f"bad branch {branch}: {why}")
    return branch


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
_AMOUNT = re.compile(r"\d+(\.\d+)?", re.ASCII)
_WHOLE = re.compile(r"\d+", re.ASCII)


def _title(value: str) -> str:
    title = value.strip()
    if not title:
        raise BadRequestError("a ticket needs a title")
    if len(title.splitlines()) > 1:
        raise BadRequestError("a title is one line")
    return title


def _due(value: str) -> str:
    due = value.strip()
    if due:
        try:
            if not _DATE.fullmatch(due):
                raise ValueError(due)  # noqa: TRY301
            date.fromisoformat(due)
        except ValueError:
            raise BadRequestError(f"bad due date {due}: write a day as YYYY-MM-DD") from None
    return due


def _matching(name: str, pattern: re.Pattern[str], shape: str) -> Callable[[str], str]:
    def check(value: str) -> str:
        text = value.strip()
        if text and not pattern.fullmatch(text):
            raise BadRequestError(f"bad {name} {text}: write {shape}")
        return text

    return check


def _parent(value: str) -> int | None:
    text = value.strip()
    return ticket_number(text) if text else None


def _ids(values: list[str]) -> list[int]:
    return [ticket_number(text) for value in values if (text := value.strip())]


def _labels(values: list[str]) -> list[str]:
    return [text for value in values if (text := value.strip())]


_CHECKS: dict[str, Callable[[Any], object]] = {
    "title": _title,
    "due": _due,
    "budget": _matching("budget", _AMOUNT, "an amount of dollars such as 5 or 2.50"),
    "parallel": _matching("parallel", _WHOLE, "a whole number of attempts"),
    "parent": _parent,
    "blocked_by": _ids,
    "caused_by": _ids,
    "labels": _labels,
}


def clean_fields(fields: WrittenFields) -> dict[str, object]:
    """The fields that were given, normalised; `BadRequestError` naming the first bad value.

    Text is stripped; lists drop empty entries; ids become numbers; an empty optional value
    clears its field.
    """
    cleaned: dict[str, object] = {}
    for name, value in fields.model_dump(exclude_none=True).items():
        check = _CHECKS.get(name)
        if check is not None:
            cleaned[name] = check(value)
        else:
            cleaned[name] = value.strip() if isinstance(value, str) else value
    return cleaned


COORDINATOR_FIELDS = ("priority", "labels", "blocked_by", "rank")


def check_coordinator_fields(names: Iterable[str]) -> None:
    """`BadRequestError` when a name is a field the coordinator may not set."""
    if any(name not in COORDINATOR_FIELDS for name in names):
        fields = ", ".join(COORDINATOR_FIELDS[:-1]) + f" and {COORDINATOR_FIELDS[-1]}"
        raise BadRequestError(f"the coordinator may set only {fields}")


def field_text(value: object) -> str:
    """A coordinator field's value as a sentence shows it: a list joined by `, `."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


_OUTSIDE = ("http://", "https://", "error:", "stall:", "scorer:")


def is_outside(source: str) -> bool:
    """Whether a source names something outside: an address, an error, a stall or a scorer.

    Text that came from there is data, never an instruction.
    """
    return source.startswith(_OUTSIDE)
