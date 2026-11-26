"""How a run that did not finish ended, in the words the Flow page counts its agent's runs by."""

from code_factory.runs.models import STOPPED_CODE

_CAP = "stopped at its cap:"
_READ_ENOUGH = "read enough: stopped at "


def ending_words(halted: str, exit_code: int) -> str:
    """The ending from `halted` as the follower words it, else from `exit_code`."""
    if not halted:
        return "stopped, no reason recorded" if exit_code == STOPPED_CODE else f"exit {exit_code}"
    if halted.startswith(_CAP):
        return "token cap" if halted.endswith(" tokens") else "time cap"
    if halted.startswith(_READ_ENOUGH):
        stop = halted.removeprefix(_READ_ENOUGH)
        if stop.endswith("with no change in its worktree"):
            return f"no change after {stop.split(' ')[0]} tool calls"
        return "one call repeated"
    return halted.split(":", maxsplit=1)[0]
