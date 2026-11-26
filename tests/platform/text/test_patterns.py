import ntpath

import pytest

from code_factory.platform.text import is_valid_pattern, name_matches


@pytest.mark.parametrize(
    ("name", "pattern", "expected"),
    [
        ("a.rs", "*.rs", True),
        ("src/a/b.rs", "*.rs", True),
        ("src/a.rs", "src/*", True),
        ("A.rs", "a.rs", False),
        ("a.rs", "?.rs", True),
        ("ab.rs", "?.rs", False),
        ("a.py", "[ab].py", True),
        ("c.py", "[!ab].py", True),
        ("a.py", "[!ab].py", False),
        ("a.rs", "*.py", False),
    ],
)
def test_name_matches(name: str, pattern: str, expected: bool) -> None:
    assert name_matches(name, pattern) is expected


@pytest.mark.parametrize("pattern", ["", "   ", "a[b", "a[!b", "a[]b", "x["])
def test_a_blank_pattern_or_unclosed_class_is_invalid(pattern: str) -> None:
    assert not is_valid_pattern(pattern)


@pytest.mark.parametrize("pattern", ["a[]b]", "a[!x]", "[[]x]", "*.py", "plain", "a[]]b"])
def test_an_ordinary_or_closed_class_is_valid(pattern: str) -> None:
    assert is_valid_pattern(pattern)


def test_a_class_holding_a_literal_opening_bracket_is_valid() -> None:
    assert is_valid_pattern("[[]")
    assert is_valid_pattern("a[[]b[c]")
    assert not is_valid_pattern("[[]b[")
    assert name_matches("[", "[[]")


def test_name_matches_is_case_sensitive_whatever_the_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("os.path.normcase", ntpath.normcase)
    assert not name_matches("A.rs", "a.rs")
    assert not name_matches("src/A.rs", "src/*.RS")
