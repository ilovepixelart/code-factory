"""What the permission reviewer said, and how many requests of a session it may answer."""

from collections.abc import Sequence
from typing import Literal

DEFAULT_LIMIT = 20  # `[agents] permission_reviewer_limit` when unset
Verdict = Literal["allow", "deny", "owner"]


def review_verdict(said: tuple[bool, str] | None) -> tuple[Verdict, str]:
    """The verdict for the reviewer's exit and output, with a denial's reason.

    `allow` on the first line counts only when the reviewer exited 0; `deny [reason]` on it is a
    denial; anything else, or no answer, is the owner's.
    """
    if said is None:
        return "owner", ""
    succeeded, out = said
    lines = out.splitlines()
    first = lines[0].strip() if lines else ""
    if first == "allow" and succeeded:
        return "allow", ""
    words = first.split(None, 1)
    if words and words[0] == "deny":
        return "deny", words[1].strip() if len(words) > 1 else ""
    return "owner", ""


def still_reviewed(verdicts: Sequence[str], limit: int) -> bool:
    """Whether the reviewer may still answer a session whose recorded verdicts are `verdicts`.

    No denial among them (a denial hands the session to the owner) and fewer than `limit` allows.
    """
    allowed = 0
    for verdict in verdicts:
        if verdict == "allow":
            allowed += 1
        elif verdict != "owner":
            return False
    return allowed < limit


def settled_verdict(verdict: Verdict, *, still_open: bool) -> Verdict:
    """An allow recorded after the session's limit filled in the meantime is the owner's."""
    return "owner" if verdict == "allow" and not still_open else verdict
