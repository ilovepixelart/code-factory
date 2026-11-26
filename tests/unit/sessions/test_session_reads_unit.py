import pytest

from code_factory.platform.errors import BadRequestError
from code_factory.sessions.models import StateFilter


def test_a_state_query_other_than_the_four_is_refused() -> None:
    with pytest.raises(
        BadRequestError, match=r"^state must be one of waiting, working, idle, stale$"
    ):
        StateFilter.from_text("ended")
