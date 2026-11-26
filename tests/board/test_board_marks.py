"""When a ticket entered its column and left the board: from its history, never its last edit."""

from datetime import UTC, datetime

from board_values import ticket
from code_factory.board.rules.marks import entered_column, left_board
from code_factory.tickets.models import ActivityMarks

CREATED = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
MOVED = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
ARCHIVED = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
TOUCHED = datetime(2026, 11, 20, 8, 0, tzinfo=UTC)
PUBLISHED = datetime(2026, 11, 18, 8, 0, tzinfo=UTC)


def test_the_column_was_entered_at_the_newest_move_into_it() -> None:
    marks = ActivityMarks(moved_to="build", moved_at=MOVED, last_at=TOUCHED)
    assert entered_column(ticket("CF-1", column="build", created_at=CREATED), marks) == MOVED


def test_a_move_into_another_column_is_not_the_entry_into_this_one() -> None:
    marks = ActivityMarks(moved_to="review", moved_at=MOVED)
    assert entered_column(ticket("CF-1", column="build", created_at=CREATED), marks) == CREATED


def test_a_ticket_never_moved_entered_its_column_when_created() -> None:
    assert entered_column(ticket("CF-1", created_at=CREATED), None) == CREATED
    assert entered_column(ticket("CF-1", created_at=CREATED), ActivityMarks()) == CREATED


def test_the_board_was_left_at_the_release_publish_time_first() -> None:
    marks = ActivityMarks(archived_at=ARCHIVED, last_at=TOUCHED)
    assert left_board(PUBLISHED, marks) == PUBLISHED.timestamp()


def test_without_a_release_the_board_was_left_at_the_last_archived_record() -> None:
    marks = ActivityMarks(archived_at=ARCHIVED, last_at=TOUCHED)
    assert left_board(None, marks) == ARCHIVED.timestamp()


def test_without_an_archived_record_the_board_was_left_at_the_last_activity() -> None:
    assert left_board(None, ActivityMarks(last_at=TOUCHED)) == TOUCHED.timestamp()


def test_without_any_record_the_board_was_left_at_zero() -> None:
    assert left_board(None, None) == 0.0
    assert left_board(None, ActivityMarks()) == 0.0
