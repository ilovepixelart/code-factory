"""A run the system killed is run again once, not failed."""

from collections.abc import Sequence
from typing import Any

from code_factory.checks.models import Action, Ran


def _entry(ran: Ran) -> dict[str, Any]:
    return {"step": ran.step, "log": ran.log, "exit_code": ran.code}


def kill_policy(runs: Sequence[Ran]) -> Action:
    """What to do after the attempts in `runs`.

    The first kill is recorded as `outcome: killed` with its step and the run goes again once; a
    second kill ends the checks and the final record carries both in `kills`.
    """
    first = runs[0]
    if len(runs) == 1:
        if not first.killed:
            return Action(rerun=False)
        return Action(rerun=True, record_kill={"outcome": "killed", "step": first.step})
    second = runs[1]
    if first.killed and second.killed:
        return Action(rerun=False, kills=[_entry(first), _entry(second)])
    return Action(rerun=False)
