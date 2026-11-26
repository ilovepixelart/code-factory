"""Defects a second reading of the module found, each pinned by the input that broke it: a
decimal past Python's digit limit, a NUL in a path, a header with a trailing comment, a deeply
nested YAML document, a tracker address with a bad port, and a quadratic scan on a cache miss."""

from datetime import date
from pathlib import Path

import pytest

from code_factory.settings.adapters import Files, lock_packages, workspace_lists
from code_factory.settings.rules import (
    ExceptionFacts,
    config_problems,
    exceptions_problems,
    lenient_config,
    parse_toml,
    tracker_allowed,
)
from code_factory.settings.rules import cross as cross_module
from code_factory.settings.rules.lines import entry_line, header_line, key_line
from code_factory.settings.rules.tool_files import deny_ignores

HUGE = "9" * 5000


def test_an_integer_past_the_digit_limit_is_a_toml_error_not_an_exception() -> None:
    text = f"[checks]\ntimeout = {HUGE}\n"
    assert parse_toml(text).__class__.__name__ == "TomlError"
    assert [p.message.startswith("toml: ") for p in config_problems("c", text)] == [True]
    assert lenient_config(text).model_dump(exclude_none=True) == {}
    found = deny_ignores(f"[advisories]\nx = {HUGE}\n")
    assert isinstance(found, str)
    assert found.startswith("toml: ")


def test_a_header_with_a_trailing_comment_is_still_a_header() -> None:
    text = '[agents] # how runs are made\nreview = true\n\n[[automations]] # one\nname = "a"\n'
    assert key_line(text, "agents", "review") == 2
    assert header_line(text, "automations") == 4
    assert entry_line(text, "automations", 0, "name") == 5


def test_a_quarantine_entry_with_a_commented_header_keeps_its_line_shapes() -> None:
    text = (
        '[[quarantine]] # flaky on CI\ntest = "tests/test_a.py::test_x"\nreason = "r"\n'
        'ticket = "CF-1"\nexpires = 2999-12-31\n'
    )
    facts = ExceptionFacts(
        tickets=frozenset({"CF-1"}), expiry_fails=True, tests={"tests/test_a.py::test_x": True}
    )
    assert exceptions_problems(text, date(2026, 11, 2), facts).problems == ()


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("https://api.linear.app:443/graphql", True),
        ("https://api.linear.app:65535/graphql", True),
        ("https://api.linear.app:abc/graphql", False),
        ("https://api.linear.app:0/graphql", False),
        ("https://api.linear.app:65536/graphql", False),
        ("https://api.linear.app:/graphql", False),
        ("http://localhost:99999", False),
        ("http://localhost:4100", True),
    ],
)
def test_a_tracker_address_with_a_bad_port_is_refused(address: str, expected: bool) -> None:
    assert tracker_allowed("linear", address) is expected


def test_unique_automation_names_cost_no_line_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "".join(
        f'[[automations]]\nname = "n{i}"\nevery = "day"\ntitle = "t"\n\n' for i in range(300)
    )
    scans = []
    real = cross_module.entry_line
    monkeypatch.setattr(cross_module, "entry_line", lambda *a: scans.append(a) or real(*a))
    assert len(lenient_config(text).automations or []) == 300
    assert scans == []


async def test_a_path_with_a_nul_reads_as_missing(tmp_path: Path) -> None:
    files = Files()
    (tmp_path / "a").write_text("x")
    assert await files.read_below(tmp_path, "a\0b", 100) is None
    assert await files.stat(tmp_path, "a\0b") is None
    assert await files.present(tmp_path, "a\0b") is False
    assert await files.names(tmp_path, "a\0b") == []


async def test_a_deeply_nested_yaml_document_is_unreadable_not_an_exception() -> None:
    deep = "a: " + "[" * 50_000 + "]" * 50_000
    assert await workspace_lists(deep) is None
    assert await lock_packages(deep) is None
