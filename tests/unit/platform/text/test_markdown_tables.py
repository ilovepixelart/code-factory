from code_factory.platform.text import Row, line_prefixes, mentions, section, section_rows
from growth import LINEAR_BOUND, growth

DECOY = (
    "# FRD\n\n### Requirements notes\n\n| ID | Note |\n|---|---|\n| CF-1-R9 | stray |\n\n"
    "## Requirements\n\n| ID | Requirement |\n|---|---|\n| CF-1-R1 | It works |\n"
)


def test_a_section_starts_only_at_its_exact_heading() -> None:
    deeper_only = "# FRD\n\n### Requirements notes\n\n| CF-1-R9 | stray |\n"
    assert section(deeper_only, "## Requirements") is None
    body = section(DECOY, "## Requirements")
    assert body is not None
    assert "CF-1-R1" in body
    assert "CF-1-R9" not in body


def test_a_heading_with_trailing_spaces_still_opens_and_the_next_section_closes() -> None:
    text = "## A   \none\n## B\ntwo\n"
    assert section(text, "## A") == "   \none"
    assert section(text, "## B") == "\ntwo\n"


def test_a_missing_heading_is_none() -> None:
    assert section("# x\n", "## Nope") is None


def test_rows_leave_out_the_header_whatever_it_says_and_the_separator() -> None:
    text = (
        "## Acceptance criteria\n\n| Id | Criterion | Check |\n|---|---|---|\n"
        "| CF-1-R1 | It works | it_works |\n"
    )
    assert [row.cells for row in section_rows(text, "## Acceptance criteria")] == [
        ("CF-1-R1", "It works", "it_works")
    ]


def test_rows_carry_their_one_based_line() -> None:
    text = "\n" * 9 + "## T\n| ID | X |\n|---|---|\n| a | b |\n| c | d |\n"
    assert section_rows(text, "## T") == [Row(("a", "b"), 13), Row(("c", "d"), 14)]


def test_a_row_with_an_empty_first_cell_is_dropped() -> None:
    text = "## T\n| ID | X |\n|---|---|\n|  | b |\n| a | b |\n"
    assert [row.cells for row in section_rows(text, "## T")] == [("a", "b")]


def test_rows_of_a_missing_section_are_none_at_all() -> None:
    assert section_rows("# x\n", "## T") == []


def test_rows_ignore_decoy_tables_in_other_sections() -> None:
    assert [row.cells[0] for row in section_rows(DECOY, "## Requirements")] == ["CF-1-R1"]


def test_mentions_needs_no_word_character_or_dash_before_and_no_digit_after() -> None:
    assert mentions("see CF-1.", "CF-1")
    assert not mentions("see CF-12", "CF-1")
    assert not mentions("XCF-1", "CF-1")
    assert not mentions("a-CF-1", "CF-1")
    assert mentions("CF-12 and CF-1", "CF-1")
    assert mentions("CF-1", "CF-1")


def test_line_prefixes_wants_the_id_at_a_line_start_without_a_digit_after() -> None:
    assert line_prefixes("x\nCF-1: done", "CF-1")
    assert not line_prefixes("x\nCF-12: done", "CF-1")
    assert not line_prefixes("see CF-1", "CF-1")


def test_a_longer_heading_with_the_same_start_does_not_open_the_section() -> None:
    assert section("## Requirements notes\nx\n", "## Requirements") is None


def test_a_large_document_without_the_heading_is_scanned_in_linear_time() -> None:
    def scan(lines: int) -> None:
        text = "a line of an ordinary document\n" * lines
        assert section(text, "## Requirements") is None
        assert section_rows(text, "## Requirements") == []

    assert growth(scan, 5_000) < LINEAR_BOUND
