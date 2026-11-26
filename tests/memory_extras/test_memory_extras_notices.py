"""The notice names, the budget refusal and the entry a draft stands for."""

from datetime import date

from code_factory.memory.models import NewMemory
from code_factory.memory_extras.rules import draft_entry, named, over_budget
from memory_extras_values import entry


def test_a_short_statement_is_named_in_quotes_whole() -> None:
    assert named("Keep it small") == '"Keep it small"'
    assert named("x" * 50) == f'"{"x" * 50}"'


def test_a_long_statement_is_cut_to_fifty_characters_ending_in_an_ellipsis() -> None:
    assert named("x" * 51) == f'"{"x" * 49}…"'


def test_the_rules_every_session_loads_passing_the_budget_are_refused_naming_by_how_much() -> None:
    rules = [entry(f"2026-11-0{n}-r", "x" * 1997) for n in range(1, 6)]
    assert over_budget(rules[:4]) is None
    assert over_budget(rules) == (
        "the rules and decisions every session loads would take 2000 characters over the "
        "memory budget of 8,000: merge, scope or retire one before adding another"
    )


def test_a_draft_stands_for_an_active_or_proposed_entry_dated_today() -> None:
    draft = NewMemory(repository="sample", kind="lesson", statement="Close it", cites=["a.py"])
    active = draft_entry(draft, date(2026, 11, 10), proposed=False)
    proposed = draft_entry(draft, date(2026, 11, 10), proposed=True)
    assert (active.date, active.status, active.cites, active.retired) == (
        date(2026, 11, 10),
        "active",
        ["a.py"],
        "",
    )
    assert proposed.status == "proposed"
    assert proposed.proposed
