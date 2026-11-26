"""The gate's heavy-step lock as the board takes it: the text `scripts/gate.sh` reads and writes."""

from dataclasses import dataclass
from typing import Literal

LOCK_FILE = "gate-heavy.lock"
BOARD_STEP = "container"
DEFAULT_WAIT = 1800


@dataclass(frozen=True)
class HeavyMove:
    """What a waiter does after reading the lock: release it, go on without it, or wait."""

    kind: Literal["release", "go_on", "wait"]
    why: str = ""


def wait_bound(setting: str | None) -> int:
    """The bound on a wait: whole seconds from the setting, anything else 1800."""
    if setting is not None and setting.isascii() and setting.isdigit():
        return int(setting)
    return DEFAULT_WAIT


def board_text(pid: int, tree: str) -> str:
    """The text of the lock the board holds for the checks of `tree`."""
    return f"{pid} {BOARD_STEP} in {tree} on the board"


def plain(text: str) -> str:
    """`text` without control characters."""
    return "".join(char for char in text if char.isprintable())


def holder_pid(held: str) -> int | None:
    """The pid a lock's text names; None when it names none."""
    word = held.split(" ", 1)[0]
    return int(word) if word and word.isascii() and word.isdigit() else None


def holder_name(held: str) -> str:
    """`pid <pid>: <step> in <tree> on <branch>`."""
    shown = plain(held)
    pid, _, rest = shown.partition(" ")
    return f"pid {pid}: {rest}"


def counts_as_holder(held: str, command: str | None) -> bool:
    """Whether a running holder counts: a gate, or the board's own lock for a container run.

    A command of None, where `ps` names nothing, counts: the bound still ends the wait.
    """
    if command is None:
        return True
    _, _, rest = held.partition(" ")
    return rest.startswith(f"{BOARD_STEP} in ") or "gate.sh" in command


def next_move(held: str, *, running: bool, counts: bool, waited: float, bound: float) -> HeavyMove:
    """What a waiter that has waited `waited` of `bound` does about the lock `held`."""
    holder = holder_name(held)
    if not running:
        return HeavyMove(
            "release", f"released the heavy-step lock of {holder}; that process is gone"
        )
    if not counts:
        return HeavyMove(
            "release", f"took over the heavy-step lock of {holder}; that process is no gate"
        )
    if waited >= bound:
        return HeavyMove(
            "go_on", f"runs without the heavy-step lock: held over {int(bound)}s, now by {holder}"
        )
    return HeavyMove("wait")
