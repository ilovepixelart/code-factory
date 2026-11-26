"""What a running gate's log and the heavy-step lock say of it, for the Team page.

The vocabulary is the `gate: ` lines `scripts/gate.sh` and the board's container wait write.
"""

from code_factory.team.models import GateProgress

CONTAINER_WAIT = "gate: checks wait for a container's turn"
_PREFIX = "gate: "
_WAITS = " waits for the heavy-step lock, held by pid "
_WAITED = " for the heavy-step lock"
_UNLOCKED = " runs without the heavy-step lock: "
_STARTS = " starts"
_PASSED = " passed in "


def _is_step(word: str) -> bool:
    return bool(word) and " " not in word


def _holder_of(held: str) -> tuple[str, str] | None:
    """The step and tree of a lock target's `<step> in <tree> on <branch>`."""
    step, found, place = held.partition(" in ")
    if not found:
        return None
    tree, found, _branch = place.rpartition(" on ")
    return (step, tree) if found else None


def _folder(tree: str) -> str:
    return tree.rstrip("/").rsplit("/", 1)[-1]


def _queued(progress: GateProgress) -> bool:
    """Whether it waits for its turn among the checks containers: a wait before any step."""
    return progress.waiting and progress.step is None


def _wait_behind(holder: str) -> tuple[str, str] | None:
    _pid, found, held = holder.partition(": ")
    parsed = _holder_of(held) if found else None
    return None if parsed is None else (_folder(parsed[1]), parsed[0])


def _restart(progress: GateProgress) -> None:
    """The log starts again with the container: forget everything but that it waits."""
    progress.step, progress.started, progress.holds_lock = None, False, False
    progress.waiting, progress.behind, progress.last_passed = True, None, None


def _read(progress: GateProgress, line: str) -> None:
    if line == CONTAINER_WAIT:
        _restart(progress)
        return
    if not line.startswith(_PREFIX):
        return
    rest = line.removeprefix(_PREFIX)
    if _queued(progress):
        progress.waiting = False
    step = rest.removesuffix(_STARTS)
    if rest.endswith(_STARTS) and _is_step(step):
        progress.step, progress.started, progress.waiting, progress.behind = step, True, False, None
    elif _WAITS in rest:
        name, _, holder = rest.partition(_WAITS)
        progress.step, progress.started, progress.waiting = name, False, True
        progress.behind = _wait_behind(holder)
    elif (rest.endswith(_WAITED) and " waited " in rest) or _UNLOCKED in rest:
        progress.waiting, progress.behind = False, None
    elif _PASSED in rest and _is_step(rest.partition(_PASSED)[0]):
        progress.last_passed = rest.partition(_PASSED)[0]
        progress.step, progress.started, progress.waiting, progress.behind = (
            None,
            False,
            False,
            None,
        )


def gate_progress(log: str, lock: str | None, tree: str) -> GateProgress:
    """What a gate's `log` lines and the heavy-step lock's target say of the gate on `tree`.

    `lock` is `<pid> <step> in <tree> on <branch>`; naming `tree` makes the gate its holder.
    """
    progress = GateProgress()
    for line in log.splitlines():
        _read(progress, line)
    held = _holder_of(lock.partition(" ")[2]) if lock is not None and " " in lock else None
    if held is not None and held[1] == tree:
        progress.step, progress.holds_lock = held[0], True
        progress.waiting, progress.behind = False, None
    return progress


def gate_line(progress: GateProgress) -> str:
    """The row's line: what it waits for, or its step, or the last step that passed."""
    if _queued(progress):
        return "waiting for a checks container's turn"
    if progress.waiting:
        if progress.behind is None:
            return "waiting for the heavy-step lock"
        place, step = progress.behind
        return f"waiting for the heavy-step lock behind {place} ({step})"
    if progress.step is not None and (progress.holds_lock or progress.started):
        return (
            f"{progress.step}, holding the heavy-step lock"
            if progress.holds_lock
            else progress.step
        )
    if progress.last_passed is not None:
        return f"after {progress.last_passed} passed"
    return "starting"
