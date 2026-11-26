"""Which failure on a tree makes a pass there flaky, and the sentence that files it."""

from collections.abc import Sequence

from code_factory.stages.models import Record
from code_factory.stages.rules.checks import exit_code_of
from code_factory.stages.rules.logs import no_verdict


def _unclean(record: Record) -> bool:
    retried = record.data.get("retried")
    return record.data.get("log_unread") is True or (isinstance(retried, list) and bool(retried))


def flaky_failure(records: Sequence[Record], tree: str) -> str | None:
    """The log of the failure on `tree` that makes a pass there flaky; `None` when there is none.

    The first failure since the last `flaky` record that is neither a system kill nor excused by
    the machine sleeping, or the first pass that is not clean while no `flaky` record names the
    tree.
    """
    counted: list[Record] = []
    tracked = False
    for record in records:
        if record.data.get("tree") != tree:
            continue
        if record.kind == "flaky":
            counted.clear()
            tracked = True
        elif (
            record.kind == "checks"
            and record.data.get("outcome") != "killed"
            and record.text("scope") != "fast"
        ):
            code = exit_code_of(record)
            if code is not None and no_verdict(code):
                continue
            failed = code != 0
            asleep = record.data.get("slept") is True
            if (failed and not asleep) or (not failed and not tracked and _unclean(record)):
                counted.append(record)
    return counted[0].text("log") if counted else None


def flaky_reason(records: Sequence[Record], ticket_id: str, tree: str, failed: str) -> str:
    """Why the bug of the log `failed` is filed: one of three forms."""
    run = next(
        (r for r in reversed(records) if r.kind == "checks" and r.text("log") == failed), None
    )
    retried = run.data.get("retried") if run is not None else None
    steps = [str(step) for step in retried] if isinstance(retried, list) else []
    opening = f"Filed by the board when the checks of {ticket_id} passed on tree {tree}"
    if steps:
        return (
            f"{opening} with {', '.join(steps)} failing and then passing when the gate ran it "
            f"again. The run is logged at {failed}."
        )
    if run is not None and run.data.get("log_unread") is True:
        return f"{opening} with a log that could not be read when they were recorded: {failed}."
    return f"{opening} after failing there. The failed run is logged at {failed}."
