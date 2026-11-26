"""A Claude Code agent file is read from its YAML front matter (the previous implementation's
`claude_agents` tests)."""

import pytest

from code_factory.agents.rules.claude_agents import parse_claude_agent
from code_factory.platform.errors import BadRequestError

FOLDED = (
    "---\nname: code-reviewer\ndescription: >-\n  Rigorous review of a diff,\n  before a PR.\n"
    "tools:\n  - Read\n  - Grep\nmodel: sonnet\ncolor: blue\n---\n\nYou review code.\n"
)
LISTED = (
    '---\nname: ticket-worker\ndescription: "Takes one ticket: to a PR"\n'
    "tools: Read, Edit ,Bash\n---\nBody\n"
)


def test_a_folded_description_and_a_tools_list_are_read() -> None:
    assert parse_claude_agent(FOLDED) == (
        "code-reviewer",
        "Rigorous review of a diff, before a PR.",
        "sonnet",
        ["Read", "Grep"],
    )


def test_a_comma_string_of_tools_is_split_trimmed_and_empty_entries_dropped() -> None:
    assert parse_claude_agent(LISTED) == (
        "ticket-worker",
        "Takes one ticket: to a PR",
        "",
        ["Read", "Edit", "Bash"],
    )
    assert parse_claude_agent("---\nname: a\ndescription: b\ntools: ' , Read,,'\n---\n")[3] == [
        "Read"
    ]


def refusal(text: str) -> str:
    with pytest.raises(BadRequestError) as caught:
        parse_claude_agent(text)
    return str(caught.value)


def test_a_file_without_front_matter_or_with_it_unclosed_is_not_an_agent() -> None:
    assert refusal("# Agent Team Coordination\n") == "no front matter"
    assert refusal("---\nname: a\ndescription: b\n") == "no front matter"


def test_a_missing_name_or_description_is_named() -> None:
    assert refusal("---\ndescription: no name here\n---\n") == "name: missing"
    assert refusal("---\nname: a\n---\n") == "description: missing"


def test_front_matter_that_does_not_parse_says_so() -> None:
    assert refusal("---\nname: [unclosed\ndescription: x\n---\n").startswith("front matter: ")


def test_front_matter_that_is_not_a_mapping_or_a_name_that_is_not_text_is_refused() -> None:
    assert refusal("---\n- a\n- b\n---\n") == "name: missing"
    assert refusal("---\nname: 5\ndescription: b\n---\n") == "name: missing"


def test_a_crlf_file_is_read() -> None:
    text = "---\r\nname: a\r\ndescription: b\r\n---\r\nbody"
    assert parse_claude_agent(text) == ("a", "b", "", [])
