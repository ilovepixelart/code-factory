"""A finding's rule name: a plain name, split off the end of a review line and checked.

Expected values are worked by hand from the previous implementation's documented rule: lower-case
words of letters and digits joined by single hyphens, a letter first, at most 40 characters; a
trailing `[rule: name]` tag on a list item, and a tag with a bad name is left in the text.
"""

import pytest

from code_factory.tickets.models import DocumentName, Problem
from code_factory.tickets.rules import plain_rule, rule_problems, split_rule, validate_document


@pytest.mark.parametrize("name", ["line-length", "a", "x1", "no-new-deps-2", "a" * 40])
def test_a_plain_rule_name_is_accepted(name: str) -> None:
    assert plain_rule(name)


@pytest.mark.parametrize(
    "name", ["", "Bad_Rule", "9lives", "a--b", "-a", "a-", "has space", "a" * 41, "café"]
)
def test_anything_else_is_not_a_plain_rule_name(name: str) -> None:
    assert not plain_rule(name)


def test_a_trailing_tag_is_split_off_the_text() -> None:
    assert split_rule("A long line [rule: line-length]") == ("A long line", "line-length")
    assert split_rule("A long line [rule:   line-length  ]  ") == ("A long line", "line-length")


def test_a_tag_that_is_not_a_plain_name_stays_in_the_text() -> None:
    text = "A long line [rule: Line Length]"
    assert split_rule(text) == (text, None)


def test_text_without_a_tag_is_whole() -> None:
    assert split_rule("A long line") == ("A long line", None)
    assert split_rule("[rule: line-length] in the middle") == (
        "[rule: line-length] in the middle",
        None,
    )


REVIEW = (
    "# Review\n\nVerdict: changes\n\nA summary [rule: Not Checked].\n\n## Findings\n\n"
    "- F1 [nit] a.py:1: fine [rule: line-length]\n"
    "- F2 [nit] a.py:2: bad [rule: Bad_Rule]\n"
    "* F3 [nit] a.py:3: also bad [rule: " + "a" * 41 + "]\n"
    "- F4 [nit] a.py:4: no tag\n"
)


def test_each_list_item_with_a_bad_rule_tag_is_a_problem_at_its_line() -> None:
    assert rule_problems(REVIEW) == [
        Problem(
            line=10,
            message=(
                'rule: "Bad_Rule" is not a plain name '
                "(lower-case words joined by hyphens, at most 40 characters)"
            ),
        ),
        Problem(
            line=11,
            message=(
                f'rule: "{"a" * 41}" is not a plain name '
                "(lower-case words joined by hyphens, at most 40 characters)"
            ),
        ),
    ]


def test_a_review_document_is_validated_for_its_rule_names_and_others_are_not() -> None:
    assert [p.line for p in validate_document(DocumentName.REVIEW, REVIEW)] == [10, 11]
    assert validate_document(DocumentName.NOTES, REVIEW) == []
