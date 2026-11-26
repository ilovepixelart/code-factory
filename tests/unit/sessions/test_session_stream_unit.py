import pytest

from code_factory.platform.errors import BadRequestError
from code_factory.sessions.service import SessionService


def test_after_beats_the_header_and_a_non_integer_is_refused_with_the_bare_sentence() -> None:
    parse = SessionService.parse_position
    assert (parse("3", "5"), parse(None, "5"), parse(None, None), parse("", "7")) == (3, 5, 0, 7)
    with pytest.raises(BadRequestError, match=r"^after must be an integer$"):
        parse("x", None)
