"""The ticket page's field and question words."""

from datetime import UTC, datetime

from board_values import ticket
from code_factory.board.rules.fields import ticket_fields

ASKED = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)


def test_lists_become_comma_text() -> None:
    shown = ticket_fields(
        ticket("CF-7", labels=["ui", "agents"], blocked_by=["CF-1", "CF-2"], caused_by=["CF-3"]),
        ASKED,
        "",
    )
    assert (shown["labels"], shown["blocked_by"], shown["caused_by"]) == (
        "ui, agents",
        "CF-1, CF-2",
        "CF-3",
    )


def test_the_stage_is_the_one_the_ticket_declares() -> None:
    assert ticket_fields(ticket("CF-7"), ASKED, "build")["stage"] == "build"
    assert ticket_fields(ticket("CF-7"), ASKED, "")["stage"] == ""


def test_the_stage_since_is_the_column_entry_given_to_the_second() -> None:
    entered = datetime(2026, 11, 20, 8, 15, 30, tzinfo=UTC)
    assert ticket_fields(ticket("CF-7"), entered, "")["stage_since"] == "2026-11-20T08:15:30Z"
