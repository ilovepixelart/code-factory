"""The refusals every entry meets on its way in (the previous implementation's field tests)."""

import pytest

from code_factory.memory.models import MemoryFields
from code_factory.memory_extras.rules import check_fields

ONE_LINE = "why, source, guard, verdict, scope, supersedes and cites are one line each"


def check(
    kind: str = "rule", statement: str = "Keep it", verdict: str = "", **fields: object
) -> str | None:
    return check_fields(kind, statement, MemoryFields(**fields), verdict)  # ty: ignore[invalid-argument-type]


def test_a_valid_entry_has_no_refusal() -> None:
    assert check(expires="2026-11-15", until="CF-9", scope="build", cites=["a.py"]) is None


def test_a_kind_outside_the_three_is_refused() -> None:
    assert check(kind="note") == "kind must be one of rule, decision, lesson"


def test_a_blank_statement_is_refused() -> None:
    assert check(statement="  \n") == "an entry needs a statement"


def test_the_kind_is_checked_before_the_statement() -> None:
    assert check(kind="note", statement="") == "kind must be one of rule, decision, lesson"


def test_each_field_holds_one_line() -> None:
    for name in ("why", "source", "guard", "scope"):
        assert check(**{name: "a\nb"}) == ONE_LINE, name
    assert check(verdict="a\nb") == ONE_LINE
    assert check(supersedes=["a", "b\nc"]) == ONE_LINE
    assert check(cites=["a\nb"]) == ONE_LINE


def test_a_malformed_expires_is_refused_and_a_date_is_not() -> None:
    assert check(expires="soon") == "expires is a date, YYYY-MM-DD"
    assert check(expires="2026-13-45") == "expires is a date, YYYY-MM-DD"
    assert check(expires="2026-11-15") is None
    assert check(expires="") is None


def test_until_names_one_ticket_id() -> None:
    assert check(until="CF-9 CF-8") == "until names one ticket id"
    assert check(until="CF-9") is None


@pytest.mark.parametrize("until", ["CF-typo", "XX-9", "CF-0", "CF-", "9", "CF-٣"])
def test_until_that_is_no_ticket_id_is_refused(until: str) -> None:
    assert check(until=until) == "until names one ticket id"


def test_the_one_line_check_comes_before_expires_and_until_and_scope() -> None:
    assert check(why="a\nb", expires="soon", until="a b", scope="bulid") == ONE_LINE
    assert check(expires="soon", until="a b", scope="bulid") == "expires is a date, YYYY-MM-DD"
    assert check(until="a b", scope="bulid") == "until names one ticket id"
