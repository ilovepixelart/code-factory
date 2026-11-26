"""What a recorded run is: active, unfinished, reported, and which state the board shows."""

from code_factory.runs.models import STOPPED_CODE, Run, RunState

RUNNER_PREFIX = "runner:"


def is_active(run: Run) -> bool:
    """A run with no exit code has not ended."""
    return run.exit_code is None


def is_unfinished(run: Run) -> bool:
    """An ended run that left work undone: a failure, or a clean exit with uncommitted work.

    A run that hit a usage limit is waiting for it to lift, not unfinished.
    """
    if run.exit_code is None or run.limited_until is not None:
        return False
    return run.uncommitted if run.exit_code == 0 else True


def is_reported(run: Run) -> bool:
    """A run a remote runner reported, not one this board started."""
    return run.agent.startswith(RUNNER_PREFIX)


def state_of(run: Run) -> RunState:
    """The one state the board shows: running, limited, stopped, failed or finished."""
    if run.exit_code is None:
        return "running"
    if run.limited_until is not None:
        return "limited"
    if run.halted or run.exit_code == STOPPED_CODE:
        return "stopped"
    return "finished" if run.exit_code == 0 else "failed"
