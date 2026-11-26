import pytest

from code_factory.runs.rules.reviews import (
    DEFAULT_LIMIT,
    review_verdict,
    settled_verdict,
    still_reviewed,
)


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ((True, "allow\n"), ("allow", "")),
        ((True, "  allow  \nmore"), ("allow", "")),
        ((False, "allow\n"), ("owner", "")),
        ((True, "deny\n"), ("deny", "")),
        ((False, "deny not today\n"), ("deny", "not today")),
        ((True, "deny   too risky  \nsecond line"), ("deny", "too risky")),
        ((True, "allowed\n"), ("owner", "")),
        ((True, "maybe\n"), ("owner", "")),
        ((True, ""), ("owner", "")),
        (None, ("owner", "")),
    ],
)
def test_a_reviewers_first_line_is_a_clear_allow_a_deny_with_a_reason_or_the_owners(
    said: tuple[bool, str] | None, expected: tuple[str, str]
) -> None:
    assert review_verdict(said) == expected


def test_a_session_is_still_reviewed_below_the_limit_with_no_denial() -> None:
    assert still_reviewed(["allow", "owner", "allow"], limit=3)


def test_a_session_at_its_limit_goes_to_the_owner() -> None:
    assert not still_reviewed(["allow", "allow", "owner"], limit=2)


def test_a_denial_hands_the_session_back_to_the_owner() -> None:
    assert not still_reviewed(["allow", "deny"], limit=20)


def test_the_default_limit_is_twenty_allows_a_session() -> None:
    assert DEFAULT_LIMIT == 20
    assert still_reviewed(["allow"] * 19, limit=DEFAULT_LIMIT)
    assert not still_reviewed(["allow"] * 20, limit=DEFAULT_LIMIT)


def test_an_allow_recorded_after_the_limit_filled_meanwhile_becomes_the_owners() -> None:
    assert settled_verdict("allow", still_open=True) == "allow"
    assert settled_verdict("allow", still_open=False) == "owner"
    assert settled_verdict("deny", still_open=False) == "deny"
    assert settled_verdict("owner", still_open=True) == "owner"
