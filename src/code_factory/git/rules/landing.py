"""Words and decisions of removing and landing."""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

NAMED = 10


class LandingChoice(BaseModel):
    """`head` is the commit to push when no merge is needed; else merge main into `first`."""

    model_config = ConfigDict(frozen=True)

    first: str
    head: str | None


def _listing(count: int, thing: str, items: Sequence[str]) -> str:
    named = ", ".join(items[:NAMED])
    more = f", and {count - NAMED} more" if count > NAMED else ""
    return f"{count} {thing}{'' if count == 1 else 's'} ({named}{more})"


def lost_words(files: Sequence[str], commits: Sequence[str]) -> str | None:
    """What removing a tree would lose, in words, at most ten of each named; `None` for nothing."""
    lost = []
    if files:
        lost.append(_listing(len(files), "uncommitted file", files))
    if commits:
        lost.append(_listing(len(commits), "unmerged commit", commits))
    return " and ".join(lost) or None


def choose_landing_head(
    *,
    clone_tip: str,
    clone_holds_main: bool,
    pushed: str | None,
    pushed_is_ours: bool,
    first_holds_main: bool,
) -> LandingChoice:
    """Which commit a landing builds on.

    The clone's tip when it already holds main's tip. Otherwise the commit on origin's branch,
    only when it holds the clone's tip and everything it adds is a two-parent merge whose tree
    equals the clean merge of its parents (`pushed_is_ours`), so a commit pushed from elsewhere
    is never taken. `first_holds_main` says whether that base holds main's tip too: then it is the
    head as it is, else a new merge commit is made on it.
    """
    if clone_holds_main:
        return LandingChoice(first=clone_tip, head=clone_tip)
    first = pushed if pushed is not None and pushed_is_ours else clone_tip
    return LandingChoice(first=first, head=first if first_holds_main else None)
