"""Review pins: which named checks a ticket's requirements cite that no test file defines.
Expected values: the previous implementation's verdicts golden test files (`test_it`,
`TestMore::test_method`, `rust_check`) and hand cases for both sides of each guard."""

import pytest

from code_factory.stages.rules import (
    check_nodes,
    is_test_file,
    named_checks,
    patterns,
    unresolved_checks,
)

PY_FILE = (
    "def test_it() -> None:\n    pass\n\n\n"
    "class TestMore:\n    def test_method(self) -> None:\n        pass\n"
)
REQUIREMENTS = (
    "# CF-1 requirements\n\n## Requirements\n\n| ID | Requirement |\n|---|---|\n"
    "| CF-1-R1 | It works |\n\n"
    "## Acceptance criteria\n\n| ID | Criterion | Named check |\n|---|---|---|\n"
    "| CF-1-R1 | Given it, then it works | test_it |\n"
    "| CF-1-R2 | Given two | `test_a`, `test_b` |\n"
    "| CF-1-R3 | Judged by a person | review |\n"
    "| CF-1-R4 | Nothing named |  |\n"
)


def test_a_field_is_a_comma_list_with_blanks_dropped() -> None:
    assert patterns("tests/a.py, ,src/*.rs,") == ["tests/a.py", "src/*.rs"]
    assert patterns("") == []


@pytest.mark.parametrize(
    "path",
    [
        "a.test.ts",
        "web/a.spec.mjs",
        "b.test.jsx",
        "test_app.py",
        "pkg/app_test.py",
        "pkg/app_test.go",
        "Tests/a.rs",
        "web/e2e/home.ts",
        "src/__tests__/x.ts",
        "spec/x.rb",
        "TEST/x.rs",
    ],
)
def test_a_file_is_a_test_by_its_name_or_its_folder(path: str) -> None:
    assert is_test_file(path)


@pytest.mark.parametrize(
    "path",
    [
        "src/test_util.rs",
        "src/a.ts",
        "a.test.py",
        "docs/testing.md",
        "src/latest/a.rs",
        "a.test.css",
    ],
)
def test_a_file_is_no_test_when_neither_its_name_nor_a_folder_says_so(path: str) -> None:
    assert not is_test_file(path)


def test_a_python_file_defines_its_functions_and_methods_by_pytest_node() -> None:
    assert check_nodes("tests/test_app.py", PY_FILE) == [
        ("test_it", "test_it"),
        ("test_method", "TestMore::test_method"),
    ]


def test_rust_go_and_script_test_files_define_their_functions() -> None:
    assert check_nodes("src/lib.rs", "#[test]\nfn rust_check() {}\n") == [
        ("rust_check", "rust_check")
    ]
    assert check_nodes("pkg/a_test.go", "func TestX(t *testing.T) {}\n") == [("TestX", "TestX")]
    assert check_nodes("web/a.test.ts", "it('works', () => {})\n") == [("works", "works")]
    assert check_nodes("web/a.spec.js", 'test("also", () => {})\n') == [("also", "also")]


def test_a_file_no_runner_reads_defines_nothing() -> None:
    assert check_nodes("README.md", "def test_it():\n  pass\n") == []
    assert check_nodes("web/a.ts", "it('x', () => {})\n") == []


def test_each_acceptance_criterion_names_its_checks_in_the_last_column() -> None:
    assert named_checks(REQUIREMENTS) == [
        ("CF-1-R1", ["test_it"]),
        ("CF-1-R2", ["test_a", "test_b"]),
        ("CF-1-R3", ["review"]),
        ("CF-1-R4", []),
    ]
    assert named_checks("# nothing\n") == []


def test_a_requirement_with_no_named_check_or_an_undefined_one_is_unresolved() -> None:
    found = unresolved_checks(named_checks(REQUIREMENTS), {"test_it", "test_a"})

    assert found == ["CF-1-R2: test_b", "CF-1-R4: no named check"]


def test_the_check_named_review_is_never_unresolved_in_any_case() -> None:
    assert unresolved_checks([("R1", ["Review"]), ("R2", ["REVIEW"])], set()) == []


def test_a_check_defined_only_in_a_file_no_runner_reads_stays_unresolved() -> None:
    defined = {name for name, _ in check_nodes("README.md", "fn rust_check() {}\n")}

    assert unresolved_checks([("CF-2-R1", ["rust_check"])], defined) == ["CF-2-R1: rust_check"]
