from datetime import UTC, datetime

import pytest

from code_factory.runs.models import DayUsage, Run
from code_factory.runs.rules.usage import usage_csv, usage_rows


def run(day: int, agent: str, model: str, tokens: int | None, cost: float | None) -> Run:
    return Run(
        id=f"{day:02d}{agent}{model}",
        ticket_key="CF-1",
        repository="sample",
        stage="build",
        started_at=datetime(2026, 11, day, 23, 59, tzinfo=UTC),
        agent=agent,
        model=model,
        tokens=tokens,
        cost=cost,
    )


def test_usage_is_summed_per_utc_day_agent_and_model_oldest_first() -> None:
    rows = usage_rows(
        [
            run(2, "b", "m", 10, 0.5),
            run(1, "a", "m", 100, 1.25),
            run(1, "a", "m", 50, None),
            run(1, "a", "n", None, 2.0),
        ]
    )
    assert rows == [
        DayUsage(day="2026-11-01", agent="a", model="m", runs=2, tokens=150, cost=1.25),
        DayUsage(day="2026-11-01", agent="a", model="n", runs=1, tokens=0, cost=2.0),
        DayUsage(day="2026-11-02", agent="b", model="m", runs=1, tokens=10, cost=0.5),
    ]


def test_the_csv_has_its_header_and_cost_to_the_cent() -> None:
    rows = [DayUsage(day="2026-11-01", agent="a", model="m", runs=2, tokens=150, cost=1.256)]
    assert usage_csv(rows) == "day,agent,model,runs,tokens,cost\n2026-11-01,a,m,2,150,1.26\n"


@pytest.mark.parametrize(
    ("lead", "cell"),
    [
        ("=", "'=cmd"),
        ("+", "'+cmd"),
        ("-", "'-cmd"),
        ("@", "'@cmd"),
        ("\t", "'\tcmd"),
        ("\r", '"\'\rcmd"'),
    ],
)
def test_a_field_a_spreadsheet_would_run_as_a_formula_gets_a_leading_quote(
    lead: str, cell: str
) -> None:
    row = DayUsage(day="2026-11-01", agent=f"{lead}cmd", model="m")
    assert usage_csv([row]) == f"day,agent,model,runs,tokens,cost\n2026-11-01,{cell},m,0,0,0.00\n"


def test_a_field_holding_a_comma_a_quote_or_a_newline_is_quoted() -> None:
    row = DayUsage(day="2026-11-01", agent='a,"b"', model="x\ny")
    assert usage_csv([row]) == (
        'day,agent,model,runs,tokens,cost\n2026-11-01,"a,""b""","x\ny",0,0,0.00\n'
    )
