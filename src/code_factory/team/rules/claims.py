"""The claim on a ticket: who holds it, and how long without a heartbeat."""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from code_factory.team.models import Lease, TeamRun

LEASE_SECONDS = 60.0


class ClaimHeld(Exception):  # noqa: N818  # a sentence for the person, not an error name
    """The ticket's claim holds; `str(error)` says who holds it."""


def _under(lease: Lease, runs: Sequence[TeamRun]) -> list[TeamRun]:
    return [run for run in runs if run.id in lease.runs]


def holds(lease: Lease, runs: Sequence[TeamRun], now: float) -> bool:
    """Whether the claim holds: a run of it is active, or none is recorded and its beat is fresh."""
    recorded = _under(lease, runs)
    if any(run.active for run in recorded):
        return True
    return not recorded and now - lease.beat_at < LEASE_SECONDS


def who(agent: str) -> str:
    """How the board names an agent: its name, or `the default agent` when empty."""
    return agent or "the default agent"


def claim(
    leases: Mapping[str, Lease], key: str, agent: str, runs: Sequence[TeamRun], now: float
) -> Lease:
    """A new claim of the ticket `key` for `agent`; `ClaimHeld` while its claim holds."""
    held = leases.get(key)
    if held is not None and holds(held, runs, now):
        msg = f"{who(held.agent)} holds this ticket"
        raise ClaimHeld(msg)
    return Lease(agent=agent, runs=(), claimed_at=now, beat_at=now)


def kept(leases: Mapping[str, Lease], runs: Sequence[TeamRun], now: float) -> dict[str, Lease]:
    """The claims that hold, each beaten to `now` while one of its runs is active."""
    result: dict[str, Lease] = {}
    for key, lease in leases.items():
        if not holds(lease, runs, now):
            continue
        active = any(run.active for run in _under(lease, runs))
        result[key] = replace(lease, beat_at=now) if active else lease
    return result


def busy(leases: Mapping[str, Lease], runs: Sequence[TeamRun], now: float) -> dict[str, str]:
    """The defined agents whose claim holds, each to the key of its ticket."""
    return {
        lease.agent: key for key, lease in leases.items() if lease.agent and holds(lease, runs, now)
    }
