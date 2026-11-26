"""The small checks a config value is held to. Expected values are the previous implementation's
cases (its path-pattern, ticket-prefix, host:port and tracker-host tests) and hand-worked hostile
addresses."""

import pytest

from code_factory.settings.rules import (
    documents_entry,
    host_port,
    is_glob,
    is_prefix,
    key_name,
    tracker_allowed,
)


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("scripts/**", True),
        ("[a-z]*", True),
        ("a[!]b]", True),
        ("src/[ab]/**", True),
        ("a[", False),
        ("a[]", False),
        ("src/[a", False),
        ("", False),
        ("  ", False),
    ],
)
def test_a_path_pattern_has_no_unclosed_class(pattern: str, expected: bool) -> None:
    assert is_glob(pattern) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CF", True),
        ("A", True),
        ("ABCDEFGHIJ", True),
        ("A1B2", True),
        ("ABCDEFGHIJK", False),
        ("1A", False),
        ("cf", False),
        ("Cf", False),
        ("", False),
        ("C-F", False),
    ],
)
def test_a_ticket_prefix_is_one_to_ten_capitals_or_digits_letter_first(
    text: str, expected: bool
) -> None:
    assert is_prefix(text) is expected


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("a:443", True),
        ("models.example.com:443", True),
        ("127.0.0.1:9", True),
        ("a:65535", True),
        ("a", False),
        ("*:1", False),
        ("a:0", False),
        ("a:65536", False),
        ("a:+1", False),
        (":443", False),
        ("https://a:443", False),
        ("a b:1", False),
        ("a:", False),
    ],
)
def test_an_acp_host_names_a_port(entry: str, expected: bool) -> None:
    assert host_port(entry) is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("CODE_FACTORY_INTAKE_JIRA", True),
        ("CODE_FACTORY_INTAKE_JIRA_2", True),
        ("CODE_FACTORY_INTAKE_", False),
        ("CODE_FACTORY_INTAKE_linear", False),
        ("ANTHROPIC_API_KEY", False),
        ("XCODE_FACTORY_INTAKE_A", False),
        ("CODE_FACTORY_INTAKE_A-B", False),
    ],
)
def test_a_tracker_key_is_named_only_under_the_intake_prefix(name: str, expected: bool) -> None:
    assert key_name(name) is expected


@pytest.mark.parametrize(
    ("tracker", "address", "expected"),
    [
        ("linear", "https://api.linear.app/graphql", True),
        ("linear", "https://API.LINEAR.APP./graphql", True),
        ("linear", "https://api.linear.app:443/graphql", True),
        ("slack", "https://slack.com/api", True),
        ("jira", "https://acme.atlassian.net", True),
        ("jira", "http://localhost:8080/x", True),
        ("linear", "http://127.0.0.1:4100/graphql", True),
        ("linear", "https://api.linear.app.evil.com", False),
        ("linear", "https://evil.com@api.linear.app", False),
        ("linear", "https://user@api.linear.app/graphql", False),
        ("linear", "https://api.linear.app:pw@evil.com/graphql", False),
        ("jira", "http://localhost:80@evil.com", False),
        ("linear", "http://api.linear.app/graphql", False),
        ("jira", "https://acme.atlassian.net.evil.com", False),
        ("jira", "https://a.b.atlassian.net", False),
        ("jira", "https://.atlassian.net", False),
        ("jira", "https://atlassian.net", False),
        ("slack", "https://evil.example/api", False),
        ("linear", "ftp://api.linear.app", False),
        ("linear", "api.linear.app", False),
        ("other", "https://api.linear.app", False),
        ("linear", "https://api.linear.app\\.evil.com", False),
        ("linear", "https://api.linear.app\n.evil.com", False),
        ("linear", " https://api.linear.app/graphql", False),
    ],
)
def test_a_tracker_address_is_held_to_its_own_hosts(
    tracker: str, address: str, expected: bool
) -> None:
    assert tracker_allowed(tracker, address) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (["requirements"], ["requirements"]),
        (["uat", "requirements", "spec"], ["requirements", "spec", "uat"]),
        (["spec"], None),
        (["requirements", "requirements"], None),
        (["requirements", "mock"], None),
        ([], None),
        ("requirements", None),
        ([1], None),
    ],
)
def test_a_documents_entry_holds_requirements_and_comes_back_in_canonical_order(
    value: object, expected: list[str] | None
) -> None:
    result = documents_entry(value)
    assert (None if result is None else list(result)) == expected
