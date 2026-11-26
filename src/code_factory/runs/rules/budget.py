"""When a run may start and how long a limited ticket waits: budgets, the usage-limit floor."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from code_factory.agents.service import StartKit
from code_factory.runs.models import BudgetScope, RunCost

LIMIT_FLOOR_S = 300.0  # the least a ticket waits after a run ended on a usage limit
OWN_ATTEMPTS = range(1, 5)  # what a ticket's own `parallel` may ask for
CONFIGURED_ATTEMPTS = range(2, 6)  # what `[agents] attempts` may ask for


class Spent(BaseModel):
    """A budget that refuses a start: its scope, what is spent, the limit and the sentence."""

    model_config = ConfigDict(frozen=True)

    scope: Literal["ticket", "month"]
    spent: float | None
    budget: float
    note: str


def attempt_count(parallel: str, configured: int | None) -> int:
    """How many parallel attempts a build starts.

    The ticket's own `parallel` (1 to 4), else the agents setting (2 to 5), else one.
    """
    text = parallel.strip()
    if text.isascii() and text.isdigit() and int(text) in OWN_ATTEMPTS:
        return int(text)
    if configured is not None and configured in CONFIGURED_ATTEMPTS:
        return configured
    return 1


def limit_until(reset: float | None, ended: float, wait: float) -> float:
    """When a ticket whose run ended on a usage limit may start again, in epoch seconds.

    The stated reset, else `wait` seconds after the end, never sooner than the floor after it.
    """
    return max(reset if reset is not None else ended + wait, ended + LIMIT_FLOOR_S)


def period(every: Literal["day", "month"], instant: datetime) -> str:
    """The UTC day (`YYYY-MM-DD`) or month (`YYYY-MM`) of `instant`."""
    day = instant.astimezone(UTC).date().isoformat()
    return day if every == "day" else day[:7]


def _refusal(scope: BudgetScope) -> Spent:
    kit = StartKit
    note = (
        kit.spent_note(scope.spent, scope.budget)
        if scope.name == "ticket"
        else kit.month_spent_note(scope.month, scope.spent, scope.budget)
    )
    return Spent(scope=scope.name, spent=scope.spent, budget=scope.budget, note=note)


def remaining_budget(
    scopes: Sequence[BudgetScope], attempt: int, count: int
) -> float | Spent | None:
    """The dollars one run may spend, `None` for no cap, or the first scope already spent.

    A scope with `spent >= budget` refuses. The least remainder caps a run, shared among `count`
    parallel attempts when the run is one of them (`attempt > 0`).
    """
    left: float | None = None
    for scope in scopes:
        if scope.spent >= scope.budget:
            return _refusal(scope)
        own = scope.budget - scope.spent
        left = own if left is None else min(left, own)
    if left is None:
        return None
    return left / count if attempt > 0 else left


def _unknown(scope: BudgetScope, runs: Sequence[RunCost]) -> Spent | None:
    found = next((r for r in runs if r.ended and r.cost is None and r.priced), None)
    if found is None:
        return None
    whose = (
        "the ticket's budget"
        if scope.name == "ticket"
        else f"the repository's budget for {scope.month}"
    )
    note = f"{whose} (${scope.budget:.2f}) cannot be judged: run {found.id} recorded no cost"
    return Spent(scope=scope.name, spent=None, budget=scope.budget, note=note)


def review_unpaid(scopes: Sequence[BudgetScope], runs: Sequence[RunCost]) -> Spent | None:
    """Why the board does not pay for a review.

    A spent budget, else (failing closed) the first scope holding an ended run of a priced agent
    that recorded no cost, so its spend is unknown. `runs` are the runs of every scope.
    """
    spent = remaining_budget(scopes, 0, 1)
    if isinstance(spent, Spent):
        return spent
    for scope in scopes:
        if (unknown := _unknown(scope, runs)) is not None:
            return unknown
    return None
