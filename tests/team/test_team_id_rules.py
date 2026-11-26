"""A ticket's id as the team module names it: `CF-<n>`."""

import pytest

from code_factory.platform.errors import BadRequestError
from code_factory.team.rules import claim_number, claim_ticket


def test_a_ticket_number_is_written_with_its_prefix_and_read_back() -> None:
    assert claim_ticket(12) == "CF-12"
    assert claim_number("CF-12") == 12


@pytest.mark.parametrize(
    "text",
    [
        "",
        "12",
        "CF-",
        "CF-0",
        "CF-x",
        "cf-3",
        "CF--3",
        "CF-1 ",
        "CF-\u0661",
        "CF-01",
        "CF-0001",
        "CF-007",
    ],
)
def test_anything_but_cf_and_a_number_from_one_is_refused_with_the_sentence(text: str) -> None:
    with pytest.raises(BadRequestError, match=r"is not a ticket id CF-<n>: write CF and a number"):
        claim_number(text)
