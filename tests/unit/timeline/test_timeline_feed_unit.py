"""One timeline of a ticket from the tickets and the talk records, in pages.

Order worked by hand. Moment T0 is when the ticket is created, T1 is one minute later.
Records, in the order they were written:

    tickets: created (T0), stage (T1), note (T1)
    talk:    question (T0), comment (T0), message (T1)

Entries of one moment keep the order of the sources (tickets, then talk) and, within a source,
their own order (a ticket's records by id, the talk by question, answer, comment, message). That
holds in both directions: newest first reverses the moments, not the order inside one.
"""

import pytest

from code_factory.timeline.rules import page_size


@pytest.mark.parametrize(
    ("limit", "size"), [(None, 25), (1, 1), (100, 100), (101, 100), (500, 100), (0, 1), (-5, 1)]
)
def test_the_page_size_is_held_between_1_and_100(limit: int | None, size: int) -> None:
    assert page_size(limit) == size
