"""What other modules ask of the ticket service: references, lookups by source and branch,
merged and open tickets, document search, flow facts, and scratch tickets.

Expected values are worked by hand from the specs that request each method (inbox, memory-extras,
metrics, follower): a reference is `id, repository, title, column, labels, rank, branch`, the
lookups answer by exact value, and a source belongs to one ticket per repository.
"""

import pytest

from code_factory.tickets.service import (
    is_outside,
)


@pytest.mark.parametrize(
    "source", ["http://x.test/1", "https://x.test/1", "error:a1", "stall:CF-1", "scorer:daily"]
)
def test_a_source_that_names_something_outside_is_outside(source: str) -> None:
    assert is_outside(source)


@pytest.mark.parametrize("source", ["", "github:1", "errors", "ftp://x.test", "my error:1"])
def test_other_sources_are_not(source: str) -> None:
    assert not is_outside(source)
