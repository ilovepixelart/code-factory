"""Usage per UTC day, agent and model, and its CSV."""

from collections.abc import Iterable

from code_factory.runs.models import DayUsage, Run
from code_factory.runs.rules.budget import period

HEADER = "day,agent,model,runs,tokens,cost\n"
_FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")  # a spreadsheet runs a cell starting so


def usage_rows(runs: Iterable[Run]) -> list[DayUsage]:
    """The runs' usage per UTC day of their start, agent and model, oldest day first.

    A run that reported no tokens or cost adds none.
    """
    summed: dict[tuple[str, str, str], DayUsage] = {}
    for run in runs:
        key = (period("day", run.started_at), run.agent, run.model)
        row = summed.get(key) or DayUsage(day=key[0], agent=run.agent, model=run.model)
        summed[key] = row.model_copy(
            update={
                "runs": row.runs + 1,
                "tokens": row.tokens + (run.tokens or 0),
                "cost": row.cost + (run.cost or 0.0),
            }
        )
    return [summed[key] for key in sorted(summed)]


def _field(text: str) -> str:
    safe = f"'{text}" if text.startswith(_FORMULA_LEADS) else text
    if any(char in safe for char in ',"\n\r'):
        return '"' + safe.replace('"', '""') + '"'
    return safe


def usage_csv(rows: Iterable[DayUsage]) -> str:
    """The rows as CSV: a header, cost to the cent, formula-looking fields guarded, quoting."""
    lines = (
        f"{_field(r.day)},{_field(r.agent)},{_field(r.model)},{r.runs},{r.tokens},{r.cost:.2f}\n"
        for r in rows
    )
    return HEADER + "".join(lines)
