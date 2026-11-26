"""Command lines are the words of the previous implementation's `runs.golden.json` cases
(`frd-budget-model`, `custom-agent`, `rules-gated-domains`) without their prompt, and shell
splitting follows POSIX."""

import shlex

import pytest

from code_factory.agents.rules.command import CommandParts, command_for, shell_words
from code_factory.agents.rules.commands import CLAUDE, CODEX
from code_factory.platform.errors import BadRequestError


def parts(  # noqa: PLR0913  # the placeholders of a command, all optional here
    *,
    prompt: str = "P",
    permissions: str = "acceptEdits",
    remaining: float | None = None,
    settings: str | None = None,
    model: str = "",
    mcp: str = "",
    local: bool = False,
) -> CommandParts:
    return CommandParts(prompt, permissions, remaining, settings, model, mcp, local)


def test_a_claude_command_with_a_budget_settings_mcp_and_model_is_the_golden_words() -> None:
    words = command_for(
        CLAUDE,
        parts(
            permissions="bypassPermissions",
            remaining=3.456,
            settings="{S}",
            mcp="{M}",
            model="opus",
        ),
    )
    assert words == [
        "claude", "-p", "P", "--permission-mode", "bypassPermissions", "--output-format",
        "stream-json", "--verbose", "--max-budget-usd", "3.46", "--settings", "{S}",
        "--setting-sources=", "--mcp-config", "{M}", "--strict-mcp-config", "--model",
        "opus",
    ]  # fmt: skip


def test_a_bare_claude_command_leaves_out_every_optional_flag() -> None:
    assert command_for(CLAUDE, parts()) == [
        "claude", "-p", "P", "--permission-mode", "acceptEdits", "--output-format",
        "stream-json", "--verbose",
    ]  # fmt: skip


def test_the_lean_tool_list_is_for_a_local_connection_only() -> None:
    local = command_for(CLAUDE, parts(local=True))
    assert local[-2:] == ["--tools", "Bash,Read,Edit,Write,Skill"]
    assert "--tools" not in command_for(CLAUDE, parts(local=False))


def test_a_custom_template_keeps_its_quoted_word_and_fills_its_placeholders() -> None:
    template = "my-agent --task {prompt} {budget_flag} --mode={permissions} {model_flag} 'a b'"
    assert command_for(template, parts(remaining=0.5)) == [
        "my-agent", "--task", "P", "--max-budget-usd", "0.50", "--mode=acceptEdits", "a b",
    ]  # fmt: skip


def test_a_codex_command_is_the_app_server() -> None:
    assert command_for(CODEX, parts()) == ["codex", "exec"]


@pytest.mark.parametrize(
    ("dollars", "words"),
    [
        (0.125, "0.12"),
        (0.375, "0.38"),
        (2.675, "2.67"),
        (3.456, "3.46"),
        (0.5, "0.50"),
        (0.0, "0.00"),
    ],
)
def test_a_budget_is_two_decimals_rounded_half_to_even_on_the_binary_value(
    dollars: float, words: str
) -> None:
    assert command_for("a {budget_flag}", parts(remaining=dollars)) == [
        "a",
        "--max-budget-usd",
        words,
    ]


def test_a_prompt_that_looks_like_a_placeholder_stays_one_argument() -> None:
    hostile = "{model_flag} --dangerously-skip-permissions $(x)"
    words = command_for("claude {prompt}", parts(prompt=hostile))
    assert words == ["claude", hostile]


def test_doubled_braces_are_literal_and_an_unknown_name_or_a_lone_brace_is_refused() -> None:
    assert command_for("a {{x}} {prompt}", parts()) == ["a", "{x}", "P"]
    for template, why in (
        ("a {nope}", "the agent command names an unknown {nope}"),
        ("a {prompt", "the agent command has an unmatched brace"),
        ("a }", "the agent command has an unmatched brace"),
    ):
        given = parts()
        with pytest.raises(BadRequestError) as caught:
            command_for(template, given)
        assert str(caught.value) == why


@pytest.mark.parametrize(
    "text",
    [
        "a b  c",
        "a 'b c' d",
        'a "b c" d',
        r"a\ b c",
        r'a "b \" c" d',
        r'a "b \n c"',
        "a '' b",
        "x\ty\nz",
        "''",
        "a'b'c",
        "",
    ],
)
def test_shell_words_split_as_a_posix_shell_does(text: str) -> None:
    assert shell_words(text) == shlex.split(text)


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("a 'b", "No closing quotation"),
        ('a "b', "No closing quotation"),
        ("a\\", "No escaped character"),
    ],
)
def test_an_unclosed_quote_or_a_trailing_backslash_is_refused_as_shlex_says(
    text: str, why: str
) -> None:
    with pytest.raises(BadRequestError) as caught:
        shell_words(text)
    assert str(caught.value) == why
    with pytest.raises(ValueError, match=why):
        shlex.split(text)


def test_no_settings_file_of_the_worktree_loads_so_a_planted_hook_never_runs() -> None:
    words = command_for(CLAUDE, parts(settings="{S}"))
    assert "--setting-sources=" in words
    assert not any("project" in word or "local" in word for word in words)
