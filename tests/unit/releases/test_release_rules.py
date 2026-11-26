"""Release rules over plain values.

Notes and tag lists follow the previous implementation's golden (`commands/cases.golden.json`,
`releases`) and its `release` tests, with ticket ids as `CF-n`; ids in text follow the text
spec's case 20.
"""

import pytest

from code_factory.releases.models import ReleaseTicket
from code_factory.releases.rules import (
    is_version,
    listed_tags,
    newest_release,
    release_notes,
    ticket_ids_in,
    version_key,
)

MIXED = [
    ReleaseTicket(id="CF-3", title="Fix a crash", kind="bug"),
    ReleaseTicket(id="CF-1", title="Add a page", kind="feature"),
    ReleaseTicket(id="CF-2", title="Tidy", kind="refactor"),
    ReleaseTicket(id="CF-4", title="Bump", kind="upgrade"),
    ReleaseTicket(id="CF-5", title="Hot", kind="hotfix"),
]


def test_notes_group_tickets_by_section_and_kind() -> None:
    assert release_notes("1.2.0", MIXED) == (
        "# 1.2.0\n\n## Added\n- CF-1: Add a page\n\n## Changed\n- CF-4: Bump\n- CF-2: Tidy\n\n"
        "## Fixed\n- CF-3: Fix a crash\n- CF-5: Hot\n"
    )


def test_notes_without_tickets_say_nothing_was_merged() -> None:
    assert release_notes("0.1.0", []) == "# 0.1.0\n\nNothing merged since the last release.\n"


def test_a_kind_outside_the_sections_is_left_out() -> None:
    odd = [ReleaseTicket(id="CF-9", title="Odd", kind="chore")]
    assert release_notes("0.1.0", odd) == "# 0.1.0\n\nNothing merged since the last release.\n"


def test_docs_tickets_are_listed_under_changed_after_refactors() -> None:
    tickets = [
        ReleaseTicket(id="CF-7", title="Words", kind="docs"),
        ReleaseTicket(id="CF-6", title="Move", kind="refactor"),
    ]
    assert release_notes("0.2.0", tickets) == (
        "# 0.2.0\n\n## Changed\n- CF-6: Move\n- CF-7: Words\n"
    )


@pytest.mark.parametrize("good", ["0.1.0", "1.20.300"])
def test_three_decimal_numbers_are_a_version(good: str) -> None:
    assert is_version(good)


def test_a_version_number_has_at_most_nine_digits() -> None:
    assert is_version("999999999.999999999.999999999")
    assert not is_version("1000000000.0.0")
    assert not is_version("0.0." + "9" * 4301)


@pytest.mark.parametrize(
    "bad", ["1.0", "1.2.3.4", "1.2.0-rc.1", "v1.2.3", "1..3", "", "1.2.x", "1.2.3\n", "1.2.٣"]
)
def test_anything_else_is_not_a_version(bad: str) -> None:
    assert not is_version(bad)


def test_the_newest_release_is_the_highest_of_origins_tags() -> None:
    listed = (
        "a1\trefs/tags/v0.9.0\nb2\trefs/tags/v0.10.0\nc3\trefs/tags/v0.10.0^{}\n"
        "d4\trefs/tags/v1.0.0-rc.1\ne5\trefs/tags/nightly\n"
    )
    tags = listed_tags(listed)
    assert tags == [
        ("v0.9.0", "a1"),
        ("v0.10.0", "b2"),
        ("v1.0.0-rc.1", "d4"),
        ("nightly", "e5"),
    ]
    assert newest_release(name for name, _ in tags) == "v0.10.0"
    assert newest_release(["nightly"]) is None


def test_versions_order_by_their_numbers_not_their_text() -> None:
    assert version_key("0.10.0") > version_key("0.9.0")
    assert version_key("1.0.0") > version_key("0.99.99")


@pytest.mark.parametrize(
    ("notes", "ids"),
    [
        ("See CF-1.", ["CF-1"]),
        ("See CF-1, CF-2.", ["CF-1", "CF-2"]),
        ("CF-12 only", ["CF-12"]),
        ("XCF-1 and a-CF-1", []),
        ("CF-2 then CF-1 then CF-2", ["CF-2", "CF-1"]),
        ("CF-1\nCF-10 (CF-1)", ["CF-1", "CF-10"]),
        ("CF-", []),
        ("", []),
    ],
)
def test_ticket_ids_are_found_in_order_of_first_appearance(notes: str, ids: list[str]) -> None:
    assert ticket_ids_in(notes, "CF") == ids


def test_a_ticket_number_has_at_most_eighteen_digits() -> None:
    assert ticket_ids_in("CF-" + "9" * 18, "CF") == ["CF-" + "9" * 18]
    assert ticket_ids_in("CF-" + "9" * 19, "CF") == []
    assert ticket_ids_in("CF-" + "9" * 4301, "CF") == []


def test_a_different_prefix_finds_its_own_ids_only() -> None:
    assert ticket_ids_in("CF-1 and AB-2", "AB") == ["AB-2"]
