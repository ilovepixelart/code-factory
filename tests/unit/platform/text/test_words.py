import json
from pathlib import Path

import pytest

from code_factory.platform.text import one_line, quoted_list, scalar_text, span

DISPLAY = json.loads(
    (
        Path(__file__).resolve().parents[3] / "support/golden/formats/display/cases.golden.json"
    ).read_text(encoding="utf-8")
)


def test_one_line_joins_words_across_unicode_spaces() -> None:
    assert one_line(" a \u00a0 b\n\tc ") == "a b c"
    assert one_line("") == ""


@pytest.mark.parametrize(("seconds", "expected"), DISPLAY["span"])
def test_span_follows_the_previous_golden(seconds: int, expected: str) -> None:
    assert span(seconds) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(59, "59s"), (60, "1m"), (61, "1m"), (3599, "60m"), (3600, "1h"), (210, "4m"), (30, "30s"),
     (89, "1m"), (91, "2m"), (151, "3m")],
)  # fmt: skip
def test_span_boundaries(seconds: int, expected: str) -> None:
    assert span(seconds) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("x", "x"), (True, "True"), (None, "None"), (1, "1"), (1.5, "1.5"), (1e16, "1e+16")],
)
def test_scalar_text_of_a_scalar(value: object, expected: str) -> None:
    assert scalar_text(value) == expected


def test_scalar_text_of_a_container_is_none() -> None:
    assert scalar_text([1]) is None
    assert scalar_text({"a": 1}) is None


def test_quoted_list_is_the_refusal_message_form() -> None:
    assert quoted_list(["a", "it's"]) == "['a', \"it's\"]"
    assert quoted_list(["a\"b'c"]) == "['a\"b\\'c']"
    assert quoted_list([]) == "[]"
