"""The guard of an undo: what the change left must still be there."""

from collections.abc import Mapping
from typing import Any


def revert_conflict(op: Mapping[str, Any], current: Mapping[str, str]) -> str | None:
    """The refusal for the first field of `op["expect"]` that holds something else now."""
    for name, expected in op.get("expect", {}).items():
        now = current.get(name, "")
        if now != expected:
            return (
                f"{op['id']} {name} changed since: it is {now} now, "
                f"not {expected} as the change left it"
            )
    return None
