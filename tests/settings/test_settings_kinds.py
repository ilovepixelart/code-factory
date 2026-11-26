"""Each value kind accepts and refuses what the previous implementation's `setting_fits` did, with
its wording. `true` is a bool in TOML and a bool is an int in Python: strictness is pinned here."""

from typing import Annotated, Any

import pytest
from pydantic import TypeAdapter, ValidationError

from code_factory.settings.models.kinds import (
    Between,
    Count,
    Documents,
    Flag,
    Globs,
    HostPorts,
    Number,
    OneOf,
    Prefix,
    Share,
    Text,
    Texts,
    TextTable,
    TrackerAddress,
    TrackerKey,
    Whole,
)

OK = object()


def check(kind: Any, value: object) -> object:  # noqa: ANN401
    """The accepted value, or the sentence the kind refuses with."""
    try:
        return TypeAdapter(kind).validate_python(value)
    except ValidationError as error:
        (only,) = error.errors()
        assert only["type"] == "setting"
        return only["msg"]


@pytest.mark.parametrize(
    ("kind", "value", "expected"),
    [
        (Count, 1, 1),
        (Count, 0, "expected a positive integer"),
        (Count, -3, "expected a positive integer"),
        (Count, True, "expected a positive integer"),
        (Count, 1.5, "expected a positive integer"),
        (Count, "1", "expected a positive integer"),
        (Whole, 0, 0),
        (Whole, -1, "expected a whole number, 0 or more"),
        (Whole, False, "expected a whole number, 0 or more"),
        (Number, 2, 2),
        (Number, 2.5, 2.5),
        (Number, True, "expected a number"),
        (Number, "2", "expected a number"),
        (Flag, True, True),
        (Flag, False, False),
        (Flag, 1, "expected true or false"),
        (Flag, "true", "expected true or false"),
        (Text, "x", "x"),
        (Text, "", "expected text, not empty"),
        (Text, 3, "expected text, not empty"),
        (Texts, ["a", "b"], ["a", "b"]),
        (Texts, [], []),
        (Texts, "a", "expected a list of text"),
        (Texts, ["a", 1], "expected a list of text"),
        (TextTable, {"brd": "sonnet"}, {"brd": "sonnet"}),
        (TextTable, {"brd": 1}, "expected a table of text"),
        (TextTable, ["a"], "expected a table of text"),
    ],
)
def test_a_plain_kind_takes_its_own_type_only(kind: Any, value: object, expected: object) -> None:  # noqa: ANN401
    assert check(kind, value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CF", "CF"),
        ("ABCDEFGHIJ", "ABCDEFGHIJ"),
        ("ABCDEFGHIJK", "expected 1 to 10 capital letters or digits, a letter first"),
        ("1A", "expected 1 to 10 capital letters or digits, a letter first"),
        (7, "expected 1 to 10 capital letters or digits, a letter first"),
    ],
)
def test_a_prefix_is_held_at_ten_characters(value: object, expected: object) -> None:
    assert check(Prefix, value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "expected a whole number from 1 to 50"),
        (1, 1),
        (50, 50),
        (51, "expected a whole number from 1 to 50"),
        (2.0, "expected a whole number from 1 to 50"),
        (True, "expected a whole number from 1 to 50"),
    ],
)
def test_between_includes_both_ends(value: object, expected: object) -> None:
    assert check(Annotated[int, Between(1, 50)], value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "expected a number above 0 and at most 0.2"),
        (0.0, "expected a number above 0 and at most 0.2"),
        (0.001, 0.001),
        (0.2, 0.2),
        (0.21, "expected a number above 0 and at most 0.2"),
        ("0.1", "expected a number above 0 and at most 0.2"),
        (True, "expected a number above 0 and at most 0.2"),
    ],
)
def test_a_share_is_above_zero_and_at_most_its_limit(value: object, expected: object) -> None:
    assert check(Annotated[float, Share(0.2)], value) == expected


def test_one_of_names_its_words() -> None:
    kind = Annotated[str, OneOf("github", "gitlab")]
    assert check(kind, "gitlab") == "gitlab"
    assert check(kind, "bitbucket") == "expected one of github, gitlab"
    assert check(kind, 1) == "expected one of github, gitlab"


def test_a_pattern_list_names_the_first_bad_pattern_quoted() -> None:
    assert check(Globs, ["scripts/**", "src/[a", "x["]) == '"src/[a" is not a path pattern'
    assert check(Globs, ["src/[ab]/**"]) == ["src/[ab]/**"]
    assert check(Globs, "scripts") == "expected a list of text"
    assert check(Globs, [1]) == "expected a list of text"
    assert check(Globs, ['a"[']) == '"a\\"[" is not a path pattern'


def test_a_pattern_with_braces_is_reported_verbatim() -> None:
    assert check(Globs, ["{x}["]) == '"{x}[" is not a path pattern'


def test_acp_hosts_each_name_a_port() -> None:
    assert check(HostPorts, ["models.example.com:443", "127.0.0.1:9"]) == [
        "models.example.com:443",
        "127.0.0.1:9",
    ]
    assert check(HostPorts, []) == []
    words = "expected a list of <host>:<port> texts"
    for refused in (["a"], ["a:443", "b"], ["*:443"], [443], "a:443"):
        assert check(HostPorts, refused) == words


def test_documents_come_back_in_canonical_order_and_refuse_the_rest() -> None:
    assert check(Documents, ["uat", "requirements"]) == ["requirements", "uat"]
    words = "expected a list of requirements, spec and uat holding requirements, each once"
    assert check(Documents, ["spec"]) == words
    assert check(Documents, ["requirements", "requirements"]) == words


@pytest.mark.parametrize(
    ("tracker", "words"),
    [
        ("linear", "expected https://api.linear.app/graphql or an address on this machine"),
        ("slack", "expected https://slack.com/api or an address on this machine"),
        ("jira", "expected an https://<site>.atlassian.net address or one on this machine"),
    ],
)
def test_a_tracker_address_says_where_its_key_may_go(tracker: str, words: str) -> None:
    kind = Annotated[str, TrackerAddress(tracker)]
    assert check(kind, "https://evil.example.com") == words
    assert check(kind, "http://localhost:4100/x") == "http://localhost:4100/x"


def test_a_tracker_key_is_named_under_the_intake_prefix() -> None:
    assert check(TrackerKey, "CODE_FACTORY_INTAKE_LINEAR") == "CODE_FACTORY_INTAKE_LINEAR"
    assert check(TrackerKey, "ANTHROPIC_API_KEY") == (
        "expected CODE_FACTORY_INTAKE_, then capitals, digits or _"
    )
