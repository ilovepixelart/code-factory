"""The owner context fence and the redaction of contexts and keys, hand worked."""

import hashlib

import pytest

from code_factory.agents.rules.fence import (
    PROMPT_LIMIT,
    Redaction,
    context_block,
    digest,
    placeholder,
    prompt_refusal,
    unmarked,
)


def test_a_digest_is_the_first_12_hex_of_the_sha256() -> None:
    assert digest("abc") == hashlib.sha256(b"abc").hexdigest()[:12]
    assert digest("abc") == "ba7816bf8f01"


def test_the_context_block_names_the_nonce_and_the_agent_on_both_fence_lines() -> None:
    block = context_block("writer", "Be brief.", "n0nc3")
    lines = block.splitlines()
    assert lines[3] == "BEGIN OWNER CONTEXT n0nc3 FOR writer"
    assert lines[4] == "Be brief."
    assert lines[5] == "END OWNER CONTEXT n0nc3 FOR writer"
    assert block.startswith("\n\nThe owner wrote the context below for the agent writer, ")


@pytest.mark.parametrize(
    "text", ["owner context", "OWNER   CONTEXT", "Owner\tContext", "owner\ncontext"]
)
def test_text_before_the_block_cannot_forge_the_marker_in_any_case_or_spacing(text: str) -> None:
    assert "context" not in unmarked(f"x {text} y").replace("owner-context-text", "")
    assert unmarked(f"x {text} y") == "x owner-context-text y"


def test_text_without_the_marker_is_left_alone() -> None:
    assert unmarked("the owner's contexts") == "the owner's contexts"


def test_a_prompt_of_exactly_one_mebibyte_is_taken_and_one_byte_more_is_refused() -> None:
    assert prompt_refusal("a", "x" * PROMPT_LIMIT) is None
    assert prompt_refusal("a", "x" * (PROMPT_LIMIT + 1)) == (
        "agent a: the prompt with its context is 1,048,577 bytes, past the 1,048,576 a harness "
        "takes; shorten the agent's context"
    )
    assert prompt_refusal("a", "é" * (PROMPT_LIMIT // 2 + 1)) is not None  # bytes, not characters


def test_a_context_is_replaced_by_its_placeholder_as_written_and_as_json_escaped() -> None:
    redaction = Redaction.of_contexts([("writer", 'say "hi"\nnow')])
    assert redaction is not None
    stand_in = placeholder("writer", 'say "hi"\nnow')
    assert stand_in == "[owner context for writer, 12 characters]"
    assert redaction.apply('log: say "hi"\nnow end') == f"log: {stand_in} end"
    assert redaction.apply(r'{"t": "say \"hi\"\nnow"}') == '{"t": "' + stand_in + '"}'


def test_a_longer_context_holding_a_shorter_one_is_replaced_whole() -> None:
    redaction = Redaction.of_contexts([("a", "be brief"), ("b", "be brief, always")])
    assert redaction is not None
    assert redaction.apply("x be brief, always y") == "x [owner context for b, 16 characters] y"


def test_no_context_and_no_key_means_no_redaction() -> None:
    assert Redaction.of_contexts([]) is None
    assert Redaction.of_contexts([("a", "")], keys=[""]) is None


def test_a_key_value_in_a_log_line_is_replaced() -> None:
    redaction = Redaction.of_contexts([], keys=["sk-or-secret"])
    assert redaction is not None
    assert redaction.apply("Authorization: Bearer sk-or-secret!") == (
        "Authorization: Bearer [redacted key]!"
    )


def test_a_key_split_across_two_chunks_is_still_replaced() -> None:
    redaction = Redaction.of_contexts([], keys=["sk-or-secret"])
    assert redaction is not None
    stream = redaction.stream()
    out = stream.push(b"token sk-or") + stream.push(b"-secret done") + stream.finish()
    assert out == b"token [redacted key] done"
    assert b"sk-or" not in out


def streamed(redaction: Redaction, chunks: list[bytes]) -> bytes:
    stream = redaction.stream()
    return b"".join(stream.push(chunk) for chunk in chunks) + stream.finish()


@pytest.mark.parametrize(
    "text",
    [b"x abcdef y", b"abcabcdef", b"abc abc abcdef", b"zabcdefabc", b"ab abcde abcdefg", b"abcdef"],
)
def test_a_stream_cut_anywhere_gives_what_the_whole_text_gives_when_a_key_holds_another(
    text: bytes,
) -> None:
    redaction = Redaction.of_contexts([], keys=["abc", "abcdef"])
    assert redaction is not None
    whole = redaction.replaced(text)
    assert b"def" not in whole
    for cut in range(len(text) + 1):
        assert streamed(redaction, [text[:cut], text[cut:]]) == whole
    assert streamed(redaction, [text[i : i + 1] for i in range(len(text))]) == whole


def test_a_stream_that_holds_no_match_gives_back_everything_by_the_end() -> None:
    redaction = Redaction.of_contexts([], keys=["abcdef"])
    assert redaction is not None
    stream = redaction.stream()
    assert stream.push(b"hello ") + stream.push(b"world") + stream.finish() == b"hello world"


def test_a_context_with_non_ascii_text_is_also_replaced_in_its_ascii_escaped_json_form() -> None:
    redaction = Redaction.of_contexts([("w", "café \U0001f600")])
    assert redaction is not None
    stand_in = placeholder("w", "café \U0001f600")
    assert redaction.apply('{"t":"caf\\u00e9 \\ud83d\\ude00"}') == '{"t":"' + stand_in + '"}'
    assert redaction.apply("café \U0001f600") == stand_in


@pytest.mark.parametrize(
    "text", [b"xabcdefgh", b"abcdefgh abcdefgh", b"abcabcdefgh", b"zzabcdefghabc", b"abcdefg"]
)
def test_a_stream_cut_anywhere_gives_what_the_whole_text_gives_when_a_key_starts_inside_another(
    text: bytes,
) -> None:
    redaction = Redaction.of_contexts([], keys=["abc", "cdefgh"])
    assert redaction is not None
    whole = redaction.replaced(text)
    for cut in range(len(text) + 1):
        assert streamed(redaction, [text[:cut], text[cut:]]) == whole
    for first in range(len(text) + 1):
        for second in range(first, len(text) + 1):
            chunks = [text[:first], text[first:second], text[second:]]
            assert streamed(redaction, chunks) == whole
    assert streamed(redaction, [text[i : i + 1] for i in range(len(text))]) == whole


def test_a_second_key_starting_inside_a_first_one_leaks_none_of_its_bytes_into_the_stream() -> None:
    redaction = Redaction.of_contexts([], keys=["abc", "cdefgh"])
    assert redaction is not None
    stream = redaction.stream()
    out = stream.push(b"xabcdef") + stream.push(b"gh") + stream.finish()
    assert out == b"xab[redacted key]"
