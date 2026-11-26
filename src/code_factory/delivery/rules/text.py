"""The words delivery writes: pull request bodies, fix feedback, issue triage and status."""

import re
from collections.abc import Mapping, Sequence

_PRIORITY = re.compile(r"^(?:priority\W*)?(urgent|high|medium|low)$", re.IGNORECASE)
_SHORT = {"p0": "urgent", "p1": "high", "p2": "medium", "p3": "low"}
_ISSUE = re.compile(r"^(?P<repo>https://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+)/issues/\d+$")


def triage(labels: list[str]) -> tuple[str, str]:
    """(type, priority) from an issue's labels: `bug` or `feature`, the first priority label."""
    kind = "bug" if any(label.strip().lower() == "bug" for label in labels) else "feature"
    for label in labels:
        word = label.strip()
        if word.lower() in _SHORT:
            return kind, _SHORT[word.lower()]
        found = _PRIORITY.match(word)
        if found:
            return kind, str(found.group(1)).lower()
    return kind, ""


def undo_line(default: str, head: str) -> str:
    """How to undo the merge: revert the merge commit whose second parent is the shipped head."""
    return (
        f"Undo: after the merge, revert it with `git revert -m 1 $(git rev-list --merges"
        f" --parents {default} | grep ' {head}$' | cut -d' ' -f1)`."
    )


def pull_body(title: str, requirements: list[str], default: str, head: str, evidence: str) -> str:
    """The pull request body: requirements (or the title), the undo line, the evidence."""
    lines = ["Requirements:", *(f"- {row}" for row in requirements)] if requirements else [title]
    parts = ["\n".join(lines), undo_line(default, head)]
    if evidence.strip():
        parts.append(evidence.strip())
    return "\n\n".join(parts) + "\n"


def feedback_text(reason: str, url: str, names: list[str], bodies: list[str]) -> str:
    """What a fix run is told about a failed pull request."""
    if reason == "ci":
        failing = ", ".join(names) if names else "see the checks"
        return (
            f"CI failed on {url}: {failing}. Read the failing checks' logs (gh pr checks {url}),"
            " fix the cause on this branch, and keep every test green."
        )
    said = "\n\n".join(bodies) if bodies else "see the review on GitHub"
    return f"A review requested changes on {url}:\n\n{said}\n\nAddress each point on this branch."


def issue_of(source: str, repository_url: str) -> bool:
    """Whether `source` is an issue of the repository at `repository_url`."""
    found = _ISSUE.match(source)
    return found is not None and str(found.group("repo")) == repository_url.rstrip("/")


def status_body(ticket_id: str, column: str, pull: str, *, waiting: bool) -> str:
    """The one status comment the board keeps on an imported issue."""
    text = f"Tracked as {ticket_id} in code-factory: {column.capitalize()}."
    if pull:
        text += f" Pull request: {pull}."
    if waiting:
        text += " Waiting on the owner."
    return text


def intake_description(url: str, body: str) -> str:
    """A ticket description for an imported issue."""
    return f"From {url}\n\n{body}".strip()


PREFIX = "CF-"


def ticket_number(ticket_id: str) -> int:
    """The number of an id `CF-<n>`; `ValueError` for anything else."""
    digits = ticket_id.removeprefix(PREFIX)
    if digits == ticket_id or not (digits.isascii() and digits.isdigit()):
        msg = f"{ticket_id!r} is not a ticket id CF-<n>"
        raise ValueError(msg)
    return int(digits)


def ticket_id(number: int) -> str:
    """The id a person reads."""
    return f"{PREFIX}{number}"


BEHAVIOUR = "## Behaviour"


def behaviour_section(notes: str) -> str:
    """The `## Behaviour` section of a ticket's notes with its heading; empty when it has none."""
    lines = notes.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == BEHAVIOUR)
    except StopIteration:
        return ""
    body = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    text = "\n".join(body).strip()
    return f"{BEHAVIOUR}\n\n{text}" if text else ""


def _shot(data: Mapping[str, object]) -> tuple[str, int]:
    images = data.get("images")
    return str(data.get("tree"))[:12], len(images) if isinstance(images, list) else 0


def screens_line(
    records: Sequence[tuple[str, Mapping[str, object]]], kinds: tuple[str, str, str, str]
) -> str:
    """What the pull request says of the ticket's screen captures; empty when it has none.

    `records` are the capture records oldest first, `kinds` the (captured, approved, sent back,
    before) record kinds. The latest capture's tree decides its state; the latest capture of the
    default branch, when there is one, is named as the before.
    """
    captured, approved, changes, before = kinds
    shots = [data for kind, data in records if kind == captured]
    befores = [data for kind, data in records if kind == before]
    prior = ""
    if befores:
        tree, count = _shot(befores[-1])
        prior = f" Before: the default branch's tree {tree} ({count} images)."
    if not shots:
        return f"Screens:{prior}" if prior else ""
    latest = shots[-1].get("tree")
    verdicts = [
        kind for kind, data in records if kind in {approved, changes} and data.get("tree") == latest
    ]
    state = {approved: "approved by the owner", changes: "sent back by the owner"}.get(
        verdicts[-1] if verdicts else "", "waiting for the owner"
    )
    tree, count = _shot(shots[-1])
    return (
        f"Screens: the latest capture, of tree {tree} ({count} images), is {state};"
        f"{prior} The images are on the ticket's page on the board."
    )
