import json

from code_factory.runs.rules.redaction import redaction_patterns
from code_factory.runs.rules.stream import OutputRedaction


def redact(chunks: list[bytes], patterns: list[tuple[str, str]]) -> bytes:
    stream = OutputRedaction(patterns)
    return b"".join(stream.push(chunk) for chunk in chunks) + stream.finish()


def test_a_secret_split_across_chunks_is_replaced_whole() -> None:
    patterns = [("sk-very-secret", "[redacted key]")]
    assert redact([b"a sk-very-", b"secret b"], patterns) == b"a [redacted key] b"


def test_every_split_point_of_a_secret_gives_the_same_output() -> None:
    patterns = [("abcdef", "X")]
    text = b"12abcdef34abcdef"
    for cut in range(len(text) + 1):
        assert redact([text[:cut], text[cut:]], patterns) == b"12X34X", cut


def test_output_with_no_secret_comes_out_unchanged_by_the_end() -> None:
    assert redact([b"plain ", b"text\n"], [("secret", "S")]) == b"plain text\n"


def test_the_longer_pattern_wins_when_one_holds_the_other() -> None:
    patterns = [("secret", "SHORT"), ("secret and more", "LONG")]
    assert redact([b"x secret and more y"], patterns) == b"x LONG y"
    assert redact([b"x secret", b" and more y"], patterns) == b"x LONG y"


def test_a_shorter_pattern_applies_when_the_longer_does_not_complete() -> None:
    patterns = [("secret", "SHORT"), ("secret and more", "LONG")]
    assert redact([b"x secret and less"], patterns) == b"x SHORT and less"


def test_no_patterns_pass_the_output_through() -> None:
    assert redact([b"a", b"b"], []) == b"ab"


def test_a_context_is_replaced_by_its_placeholder_in_every_form_it_appears() -> None:
    text = 'Say "hi"\nthen go'
    patterns = redaction_patterns([("writer", text)], [])
    stand_in = "[owner context for writer, 16 characters]"
    assert (text, stand_in) in patterns
    assert (json.dumps(text)[1:-1], stand_in) in patterns
    assert redact([f"x {text} y".encode()], patterns) == f"x {stand_in} y".encode()


def test_a_non_ascii_context_is_also_replaced_as_a_json_ascii_escape() -> None:
    text = "café rules"
    patterns = redaction_patterns([("writer", text)], [])
    escaped = json.dumps(text, ensure_ascii=True)[1:-1]
    assert escaped != text
    assert (escaped, "[owner context for writer, 10 characters]") in patterns


def test_a_key_is_replaced_by_the_key_stand_in_and_an_empty_key_is_ignored() -> None:
    patterns = redaction_patterns([], ["sk-1", ""])
    assert patterns == [("sk-1", "[redacted key]")]


def test_an_empty_context_has_nothing_to_redact() -> None:
    assert redaction_patterns([("writer", "")], []) == []
