"""What a merge that waits for a review reads.

Which diff is small enough to merge without one, which change is the owner's, and what holds a
pull request for a review.
"""

import fnmatch
from collections.abc import Sequence
from datetime import datetime

from code_factory.stages.models import BlockingFinding, Hold, ReviewDecision

CONFIG_FILE = ".code-factory/config.toml"
_PLAIN_MODES = ("000000", "100644", "100755")
_ABSENT = _PLAIN_MODES[0]
_ENDS = 3  # a numstat record is `<added>\t<removed>\t<path>`

Changed = tuple[int | None, str]


def _count(text: str) -> int | None:
    stripped = text.strip()
    return int(stripped) if stripped.isascii() and stripped.isdigit() else None


def numstat(text: str) -> list[Changed]:
    """The files of `git diff --numstat -z --no-renames`: lines changed (none for a binary file).

    A record that is not three fields reads as a file of no known size, which no rule calls small.
    """
    files: list[Changed] = []
    for record in text.split("\0"):
        if not record.strip():
            continue
        fields = record.split("\t", 2)
        if len(fields) < _ENDS:
            files.append((None, record))
            continue
        added, removed = _count(fields[0]), _count(fields[1])
        both = None if added is None or removed is None else added + removed
        files.append((both, fields[2]))
    return files


def plain(raw: str) -> bool:
    """Whether every change of `git diff --raw -z --no-renames` is one a count of lines measures.

    To a plain file whose mode stays. A submodule's commit, a link and a mode change are not, nor
    is a record that does not read.
    """
    records = iter(raw.split("\0"))
    for record in records:
        if not record.startswith(":"):
            continue
        next(records, None)  # the path that follows a header may itself start with a colon
        modes = record[1:].split(" ")
        if len(modes) < 2:  # noqa: PLR2004  # before and after
            return False
        before, after = modes[0], modes[1]
        kept = before == after or _ABSENT in {before, after}
        if not (kept and before in _PLAIN_MODES and after in _PLAIN_MODES):
            return False
    return True


def _matches_from(names: Sequence[str], parts: Sequence[str]) -> bool:
    if not parts:
        return not names
    head, rest = parts[0], parts[1:]
    if head == "**":
        return any(_matches_from(names[skip:], rest) for skip in range(len(names) + 1))
    return bool(names) and fnmatch.fnmatchcase(names[0], head) and _matches_from(names[1:], rest)


def path_matches(path: str, pattern: str) -> bool:
    """Whether the repository path matches `pattern`.

    `**` is any number of folders; `*`, `?` and `[...]` match within one name.
    """
    names = [name for name in path.split("/") if name]
    parts = [part for part in pattern.split("/") if part]
    return _matches_from(names, parts)


def _sized(files: Sequence[Changed]) -> int | None:
    total = 0
    for lines, _ in files:
        if lines is None:
            return None
        total += lines
    return total


def small(files: Sequence[Changed], limit: int, sensitive: Sequence[str]) -> bool:
    """Whether a diff merges without a review: at most `limit` lines, every size known.

    No file is the repository's config or in a path a `sensitive` pattern names. Paths are
    compared without their case: a disk that folds case opens `Config.toml` as `config.toml`.
    """

    def guarded(path: str) -> bool:
        lower = path.lower()
        return lower == CONFIG_FILE or any(path_matches(lower, p.lower()) for p in sensitive)

    total = _sized(files)
    return total is not None and total <= limit and not any(guarded(path) for _, path in files)


def change_hold(
    files: Sequence[Changed], large_change: int | None, sensitive_paths: Sequence[str]
) -> str | None:
    """Why a diff is the owner's to merge: a sensitive file, else a change past `large_change`."""
    for _, path in files:
        lower = path.lower()
        if lower == CONFIG_FILE:
            return f"Sensitive path: {path} is the repository's config"
        pattern = next((p for p in sensitive_paths if path_matches(lower, p.lower())), None)
        if pattern is not None:
            return f"Sensitive path: {path} matches {pattern}"
    if large_change is None:
        return None
    total = _sized(files)
    if total is None:
        return f"Large change: its size cannot be counted, against large_change {large_change}"
    if total > large_change:
        return f"Large change: {total} changed lines, over large_change {large_change}"
    return None


def findings_note(blocking: Sequence[BlockingFinding]) -> str:
    """What the Inbox says of a pull request its blocking findings hold."""
    listed = "; ".join(f"{f.id} [{f.severity}] {f.text}" for f in blocking)
    return f"Review before merge: {listed}"


def review_hold_decision(  # noqa: PLR0913  # the facts of one decision, all named
    *,
    review_on: bool,
    small: bool,
    passed: bool,
    blocking: Sequence[BlockingFinding],
    ended: bool,
    skipped_note: str | None,
    ready_since: datetime | None,
    run_timeout: int,
    review_active: bool,
    now: datetime,
    head: str,
) -> Hold | None:
    """Why a ready pull request at `head` is not merged on its own; `None` when nothing holds.

    `passed` is the latest verdict being a pass of the head's code; `ended` a review run of the
    same code that is no longer active. It waits on the owner once a review of the head ended
    without clearing it or was skipped, or none ended within `run_timeout` seconds of the head
    becoming ready while none runs. A head no record dates has waited an unknown time.
    """
    if not review_on or small or (passed and not blocking):
        return None
    short = head[:7]
    owner = _owner_hold(
        blocking=blocking if passed or ended else (),
        ended=ended,
        skipped_note=skipped_note,
        short=short,
    )
    if owner is not None:
        return Hold(reason=owner, owner=True)
    waited = None if ready_since is None else (now - ready_since).total_seconds()
    if (waited is None or waited > run_timeout) and not review_active:
        return Hold(
            reason=f"Review before merge: no review of {short} ended within {run_timeout} s",
            owner=True,
        )
    return Hold(reason=f"Review before merge: waits for the review of {short}", owner=False)


def _owner_hold(
    *, blocking: Sequence[BlockingFinding], ended: bool, skipped_note: str | None, short: str
) -> str | None:
    if blocking:
        return findings_note(blocking)
    if ended:
        return f"Review before merge: the review of {short} ended without a pass"
    if skipped_note is not None:
        return f"Review before merge: the review of {short} was skipped ({skipped_note})"
    return None


def review_outcome(verdict: str, *, blocking_open: bool, returned: int, cap: int) -> ReviewDecision:
    """`changes` when a blocking finding is open or the verdict asks for changes; `halt` at the cap.

    `returned` is how many times the review returned the ticket before. A pass is `pass`.
    """
    if not (blocking_open or verdict == "changes"):
        return "pass"
    return "halt" if returned >= cap else "changes"
