"""Knowledge search: ranking, snippets, plain text and the address a result opens."""

import pytest

from code_factory.memory_extras.models import Doc
from code_factory.memory_extras.rules import (
    address,
    entry_text,
    github_web,
    plain_snippet,
    rank,
    scores,
    snippet,
    words_of,
)
from memory_extras_values import entry


def test_a_query_is_split_into_lowercase_alphanumeric_words() -> None:
    assert words_of("Keep  small, the_gate!") == ["keep", "small", "the", "gate"]
    assert words_of("  ?! ") == []


def test_bm25_of_a_word_held_by_one_of_two_documents_is_floored_as_fts5_floors_it() -> None:
    # N=2, n=1: idf = ln((2 - 1 + 0.5) / (1 + 0.5)) = 0, floored to 1e-6 (SQLite's FTS5 answers
    # bm25 = -1.375e-06 for this corpus). d1: tf=2, dl=3, avgdl=3: 2 * 2.2 / 3.2 = 1.375.
    one = Doc(path="a.md", text="gate gate keep")
    other = Doc(path="b.md", text="keep small docs")
    assert scores([one, other], ["gate"]) == [(one, pytest.approx(1.375e-6))]


def test_a_word_held_by_six_of_ten_documents_scores_the_floor_not_a_positive_weight() -> None:
    # idf = ln(4.5 / 6.5) < 0, so FTS5 floors it to 1e-6; with tf=1, dl=avgdl=2: 1e-6 * 2.2 / 2.2.
    docs = [Doc(path=f"{i}.md", text="gate x" if i < 6 else "y z") for i in range(10)]
    found = scores(docs, ["gate"])
    assert [score for _, score in found] == [pytest.approx(1e-6)] * 6


def test_a_shorter_document_holding_the_word_once_ranks_before_a_longer_one() -> None:
    short = Doc(path="z.md", text="keep")
    long = Doc(path="a.md", text="keep small docs gate")
    assert rank([long, short], ["keep"]) == [short, long]


def test_a_document_missing_any_word_is_not_a_result() -> None:
    both = Doc(path="a.md", text="keep it small")
    one = Doc(path="b.md", text="keep going")
    assert rank([one, both], ["keep", "small"]) == [both]
    assert rank([one, both], []) == []


def test_a_word_matches_a_whole_word_in_any_case_and_not_a_part_of_one() -> None:
    assert rank([Doc(path="a.md", text="The GATE refuses")], ["gate"]) != []
    assert rank([Doc(path="a.md", text="gates and gated")], ["gate"]) == []


def test_documents_scoring_alike_come_in_path_order() -> None:
    first = Doc(path="a.py", text="keep small")
    second = Doc(path="b.md", text="keep small")
    assert rank([second, first], ["keep"]) == [first, second]


def test_a_snippet_of_a_short_text_is_the_whole_text() -> None:
    assert snippet("The gate ran twice", ["gate"]) == "The gate ran twice"


def numbered(count: int) -> str:
    return " ".join(f"w{n}" for n in range(count))


def test_a_snippet_is_a_window_of_twelve_words_holding_the_query_with_ellipses_where_cut() -> None:
    text = numbered(14) + " gate " + numbered(5)
    # `gate` is token 14 of 20; the first window of 12 tokens holding it starts at token 3.
    assert snippet(text, ["gate"]) == "..." + " ".join(f"w{n}" for n in range(3, 14)) + " gate..."


def test_a_snippet_at_the_start_of_a_long_text_cuts_only_the_end() -> None:
    assert snippet("gate " + numbered(20), ["gate"]) == "gate " + numbered(11) + "..."


def test_a_snippet_prefers_the_window_holding_the_most_query_words() -> None:
    text = "gate " + numbered(30) + " keep gate"
    assert (
        snippet(text, ["gate", "keep"])
        == "..." + " ".join(f"w{n}" for n in range(20, 30)) + " keep gate"
    )


def test_plain_text_drops_fences_rules_marks_and_pipes() -> None:
    raw = "```sh\n## Heading\n> quoted\n- item `code` **bold**\n| a | b |\n|---|---|\n1. first\n---"
    assert plain_snippet(raw) == "Heading quoted item code bold a b first"


def test_plain_text_joins_lines_by_single_spaces() -> None:
    assert plain_snippet("  one \n\n two\tthree  ") == "one two three"


@pytest.mark.parametrize(
    ("remote", "web"),
    [
        ("git@github.com:owner/name.git", "https://github.com/owner/name"),
        ("https://github.com/owner/name", "https://github.com/owner/name"),
        ("https://github.com/owner/name.git\n", "https://github.com/owner/name"),
        ("ssh://git@github.com/owner/name.git", "https://github.com/owner/name"),
        ("https://gitlab.com/owner/name", None),
        ("https://github.com/", None),
        ("", None),
    ],
)
def test_the_web_address_of_a_github_remote(remote: str, web: str | None) -> None:
    assert github_web(remote) == web


def test_a_result_opens_the_ticket_page_the_memory_entry_or_the_file_on_github() -> None:
    web = "https://github.com/owner/name"
    assert address("sample repo", "tickets/CF-7/spec.md", web) == "/tickets/sample%20repo/CF-7"
    assert address("sample", "memory/2026-10-01-keep", web) == "#2026-10-01-keep"
    assert address("sample", "docs/notes.md", web) == f"{web}/blob/HEAD/docs/notes.md"
    assert address("sample", "docs/notes.md", "") == ""


def test_a_file_address_encodes_each_path_component_and_keeps_the_separators() -> None:
    web = "https://github.com/owner/name"
    assert address("sample", "docs/C# notes.md", web) == f"{web}/blob/HEAD/docs/C%23%20notes.md"


def test_an_entry_is_searched_as_its_set_fields_then_its_statement() -> None:
    held = entry(
        "2026-10-02-gate", "The gate ran twice on one tree", source="CF-2", cites=["a.py", "b_test"]
    )
    assert entry_text(held) == (
        "kind: rule\ndate: 2026-10-02\nsource: CF-2\ncites: a.py, b_test\n"
        "The gate ran twice on one tree"
    )
