"""What a run costs when its runtime reports tokens and no cost, and the budgets that stop it."""

import math
from collections.abc import Mapping

from code_factory.agents.models.usage import Price
from code_factory.agents.rules.logs import amount

MILLION = 1_000_000.0
Parts = tuple[int, int]


def _price_of(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) and value >= 0 else None


def agent_price(
    input_price: float | None, output_price: float | None, *, local: bool
) -> Price | None:
    """The price a run of an agent is estimated at.

    The one its definition names (both prices), else 0 when its connection is served on this
    machine, where a token is not billed, else none.
    """
    named = (_price_of(input_price), _price_of(output_price))
    if named[0] is not None and named[1] is not None:
        return Price(input=named[0], output=named[1])
    return Price(input=0.0, output=0.0) if local else None


def estimate(price: Price, parts: Parts) -> float:
    """The dollars `parts` (input and output tokens) cost at `price`."""
    return (parts[0] * price.input + parts[1] * price.output) / MILLION


def spent_parts(logged: Parts | None, reported: Parts | None) -> Parts | None:
    """The tokens a run spent: the log's or the reported requests', whichever holds more.

    The log's when they hold as much, neither lowering the other.
    """
    if logged is not None and reported is not None and sum(reported) > sum(logged):
        return reported
    return logged if logged is not None else reported


def costs_so_far(spent: Mapping[str, Parts | None], price: Price | None) -> dict[str, float | None]:
    """Each run's cost so far, an estimate from the tokens it spent; none at no price or tokens."""
    return {
        run: None if price is None or parts is None else estimate(price, parts)
        for run, parts in spent.items()
    }


def ticket_budget(own: str, configured: object) -> float | None:
    """The ticket's budget in dollars: its own field, else the configuration's, else none."""
    named = amount(own) if own else None
    return named if named is not None else amount(configured)


def monthly_budget(configured: object) -> float | None:
    """The repository's budget in dollars for each UTC month, if any."""
    return amount(configured)
