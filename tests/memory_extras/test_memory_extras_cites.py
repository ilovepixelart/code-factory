"""What an entry cites, whether it still exists, and the restatement of CLAUDE.md."""

from code_factory.memory_extras.rules import gone_cites, plain_cite, restated, stale_mark
from memory_extras_values import entry


def test_a_cited_path_or_test_that_is_missing_is_gone_and_present_ones_are_not() -> None:
    cited = entry(cites=["src/kept.rs", "src/removed.rs", "kept_test", "removed_test"])
    gone = gone_cites(cited, frozenset({"kept_test"}), lambda cite: cite == "src/kept.rs")
    assert gone == ["src/removed.rs", "removed_test"]


def test_an_entry_citing_nothing_has_no_cite_gone() -> None:
    assert gone_cites(entry(), frozenset(), lambda _: False) == []
    assert gone_cites(entry(cites=["", " "]), frozenset(), lambda _: False) == []


def test_an_absolute_or_parent_cite_counts_as_gone_even_when_it_exists() -> None:
    cited = entry(cites=["/etc/hosts", "../secret", "a/../../b", "ok/path.py"])
    assert gone_cites(cited, frozenset(), lambda _: True) == [
        "/etc/hosts",
        "../secret",
        "a/../../b",
    ]


def test_a_plain_cite_is_relative_and_stays_below_its_root() -> None:
    assert plain_cite("src/a.py")
    assert plain_cite("a..b/c")
    assert not plain_cite("/abs")
    assert not plain_cite("..")
    assert not plain_cite("x/../y")
    assert not plain_cite("")


def test_the_stale_mark_names_each_cite_that_is_gone() -> None:
    assert stale_mark(["a.py", "b_test"]) == " [stale: cites a.py, b_test no longer exist]"
    assert stale_mark([]) == ""


CLAUDE = (
    "# Rules\n\n- Commits and pull requests carry no AI attribution of any kind.\n"
    "- Build it, run the tests the change reaches\n  and commit.\n"
)


def test_a_statement_restating_a_claude_md_line_is_named_with_that_line() -> None:
    hit = restated("Commits and pull requests carry no AI attribution of any kind", CLAUDE)
    assert hit == (3, "Commits and pull requests carry no AI attribution of any kind.")


def test_case_and_punctuation_do_not_hide_a_restatement_and_a_wrapped_line_is_one_line() -> None:
    hit = restated("RUN the tests the change reaches, and commit!", CLAUDE)
    assert hit is not None
    assert hit[0] == 4


def test_a_statement_that_merely_shares_words_is_not_a_restatement() -> None:
    assert restated("Run the tests before you commit anything", CLAUDE) is None


def test_three_words_are_not_a_restatement_and_an_empty_file_has_none() -> None:
    assert restated("run the tests", CLAUDE) is None
    assert restated("anything at all, no file", "") is None


def test_a_line_longer_than_the_statement_that_holds_it_is_a_restatement() -> None:
    hit = restated("pull requests carry no AI attribution", CLAUDE)
    assert hit is not None
    assert hit[0] == 3


def test_a_heading_closes_a_block() -> None:
    claude = "first words of a block\n# Heading\nsecond block of words here\n"
    assert restated("a block heading second", claude) is None
    assert restated("a block second block", claude.replace("# Heading\n", "")) is not None
