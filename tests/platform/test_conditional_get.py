"""Conditional GET as RFC 9110 section 13.1.2 defines it."""

import pytest

from code_factory.platform.web.conditional import etag_of, matches, still_matches

TAG = etag_of('{"a": 1}')


def test_the_tag_is_a_quoted_digest_of_the_bytes() -> None:
    assert TAG.startswith('"')
    assert TAG.endswith('"')
    assert etag_of('{"a": 1}') == TAG
    assert etag_of('{"a": 2}') != TAG


@pytest.mark.parametrize(
    "header",
    [TAG, f"W/{TAG}", f'"other", {TAG}', f' "x" ,W/{TAG} ', "*"],
)
def test_a_header_naming_the_tag_weakly_or_in_a_list_or_star_matches(header: str) -> None:
    assert matches(header, TAG)


@pytest.mark.parametrize("header", [None, "", '"other"', TAG.strip('"'), '"other", "else"'])
def test_a_header_without_the_tag_does_not_match(header: str | None) -> None:
    assert not matches(header, TAG)


@pytest.mark.parametrize(
    ("if_match", "goes_ahead"),
    [
        (None, True),
        ('"abc"', True),
        ('"old", "abc"', True),
        ("*", True),
        ('"old"', False),
        ('W/"abc"', False),
        ("", False),
    ],
)
def test_a_write_goes_ahead_only_while_if_match_names_the_tag_strongly(
    if_match: str | None, goes_ahead: bool
) -> None:
    assert still_matches(if_match, '"abc"') is goes_ahead
