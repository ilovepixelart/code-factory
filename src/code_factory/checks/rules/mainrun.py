"""When main's run is due, which step failed, the search for the merge, and a streak."""

import re
from collections.abc import Callable, Collection, Mapping, Sequence

from code_factory.checks.models import MainRecord

CAUSE_CHARS = 120
BEFORE_ANY_STEP = "before any step"
_TICKET = re.compile(r"(?<![A-Za-z\d])CF-\d+(?!\d)", re.ASCII)


def main_due(recorded: MainRecord | None, tip: str) -> bool:
    """Whether a run is due on `tip`: none ran on it, or a failing one's search was cut short."""
    if recorded is None or recorded.commit != tip:
        return True
    return recorded.failed and bool(recorded.passed) and not recorded.searched


def failed_step(reported: Sequence[tuple[str, str]]) -> str:
    """The first step a gate's log leaves failed; empty when it names none."""
    return next((step for step, state in reported if state == "failed"), "")


def cause_before_any_step(log: str) -> str:
    """What a run that failed before any step is recorded as: the log's last line, cut."""
    lines = [line.strip() for line in log.splitlines() if line.strip()]
    last = lines[-1][:CAUSE_CHARS] if lines else ""
    return f"{BEFORE_ANY_STEP}: {last}" if last else BEFORE_ANY_STEP


class Bisection:
    """A search for the first of `count` commits, oldest first, on which a run fails.

    The commits before it pass and every one after it fails, as a merge that broke the run leaves
    them. With `last_fails` the last commit is known to fail and is not asked. Ask `next_index`,
    run that commit, `answer` whether it failed, and repeat until `next_index` is None.
    """

    def __init__(self, count: int, *, last_fails: bool) -> None:
        self._count = count
        self._low = 0
        self._high = max(count - 1, 0) if last_fails else count

    def next_index(self) -> int | None:
        """The commit to run next; None when the search is done."""
        if self._low >= self._high:
            return None
        return self._low + (self._high - self._low) // 2

    def answer(self, *, failed: bool) -> None:
        """Record whether the commit last asked failed."""
        middle = self._low + (self._high - self._low) // 2
        if failed:
            self._high = middle
        else:
            self._low = middle + 1

    @property
    def found(self) -> int | None:
        """The first failing commit; None when every commit asked passed."""
        return self._low if self._low < self._count else None


def bisect(count: int, last_fails: bool, fails: Callable[[int], bool]) -> int | None:
    """`Bisection` run with a synchronous `fails`; an error from it ends the search."""
    steps = Bisection(count, last_fails=last_fails)
    while (index := steps.next_index()) is not None:
        steps.answer(failed=fails(index))
    return steps.found


def complete_main(
    previous: MainRecord | None, run: MainRecord, *, step: str, reason: str
) -> MainRecord:
    """`run` with what the record before it adds.

    A pass moves `passed` to its commit. A failure keeps the last pass, names its `step` and (for
    a code above 0) its `reason`, and a streak on the same step keeps the merge it blamed.
    """
    if not run.failed:
        return run.model_copy(update={"passed": run.commit})
    update: dict[str, object] = {"step": step, "reason": reason if run.exit_code > 0 else ""}
    if previous is not None:
        update["passed"] = previous.passed
        streak = previous.exit_code > 0 and previous.searched and previous.step == step
        if streak and run.exit_code > 0:
            update["broken_by"] = previous.broken_by
            update["searched"] = True
    return run.model_copy(update=update)


def ticket_ids(text: str) -> list[str]:
    """The ticket ids in `text`, upper-cased, in order."""
    return [found.upper() for found in _TICKET.findall(text.upper())]


def blame_ticket(branch: str, second_parent_subject: str, known: Collection[str]) -> str:
    """The ticket a merge brought in.

    An id in the merged branch's name that names a known ticket, else the first id of the second
    parent's subject, else any id in the branch's name; empty when none.
    """
    in_branch = ticket_ids(branch)
    named = next((ticket for ticket in in_branch if ticket in known), None)
    if named is not None:
        return named
    return next(iter([*ticket_ids(second_parent_subject), *in_branch]), "")


def first_parent_merges(parents: Mapping[str, Sequence[str]], tip: str) -> list[str]:
    """The merge commits on the first-parent line from `tip` back, oldest first.

    `parents` maps each commit of the range to its parents; the line ends at the first commit
    outside it.
    """
    merges = []
    commit: str | None = tip
    while commit is not None and commit in parents:
        found = parents[commit]
        if len(found) > 1:
            merges.append(commit)
        commit = found[0] if found else None
    return merges[::-1]
