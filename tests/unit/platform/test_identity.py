from code_factory.platform.identity import redact

TOKEN = "cfr_" + "A" * 43


def test_a_token_in_a_log_line_is_replaced_by_its_prefix_and_a_marker() -> None:
    assert redact(f"Authorization: Bearer {TOKEN} for run 7") == (
        "Authorization: Bearer cfr_[redacted] for run 7"
    )


def test_every_token_in_the_text_is_redacted_whatever_its_kind() -> None:
    other = "cfo_" + "b-_" * 14 + "b"
    assert redact(f"{TOKEN},{other}") == "cfr_[redacted],cfo_[redacted]"


def test_text_that_only_resembles_a_token_is_left_alone() -> None:
    short = "cfr_" + "A" * 42
    assert redact(f"{short} cf_{'A' * 43} xcfr") == f"{short} cf_{'A' * 43} xcfr"
