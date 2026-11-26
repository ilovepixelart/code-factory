"""The message for an Inbox item, the target's address rule and what a reply may say."""

import pytest

from code_factory.push.rules import address_refusal, bad_reply, message

TICKET = {"repository": "sample", "id": "CF-7", "title": "x"}


@pytest.mark.parametrize(
    ("format_", "url", "refusal"),
    [
        ("ntfy", "https://ntfy.sh/topic", None),
        ("webhook", "http://127.0.0.1:9000/hook", None),
        ("webhook", "http://localhost/hook", None),
        ("email", "https://ntfy.sh/topic", "a push format is ntfy or webhook"),
        (
            "ntfy",
            "http://ntfy.sh/topic",
            "plain http goes only to localhost or 127.0.0.1; use https://",
        ),
        ("ntfy", "ftp://ntfy.sh/topic", "a push address is an http or https URL"),
        (
            "ntfy",
            "https://me:pw@ntfy.sh/topic",
            "a push address carries no user, password or fragment",
        ),
    ],
)
def test_a_target_is_taken_only_at_a_plain_address(
    format_: str, url: str, refusal: str | None
) -> None:
    assert address_refusal(format_, url) == refusal


def test_a_question_is_announced_with_its_identity_for_a_reply_link() -> None:
    item = {"ticket": TICKET, "question": {"document": "spec.md", "index": 0, "text": "Which?"}}
    found = message("questions", item)
    assert found is not None
    assert (found.text, found.question) == (
        "CF-7: a question waits for your answer",
        ("sample", "CF-7", "spec.md", "0", "Which?"),
    )


def test_a_failing_default_branch_names_its_repository() -> None:
    found = message("main", {"main": {"repository": "sample", "passed": "abc"}})
    assert found is not None
    assert (found.text, found.anchor) == (
        "sample: the default branch fails its checks",
        "main-sample",
    )


def test_a_pull_request_out_of_fix_rounds_says_what_they_left() -> None:
    item = {"ticket": TICKET, "kind": "stuck", "note": "3 rounds failed", "reason": "r"}
    found = message("failing", item)
    assert found is not None
    assert found.text == "CF-7: 3 rounds failed"


def test_a_section_that_needs_no_reply_sends_nothing() -> None:
    assert message("rules", {"ticket": TICKET}) is None


@pytest.mark.parametrize(
    ("choices", "answer", "refusal"),
    [
        (["Blue"], "", None),
        ([], "Teal", None),
        ([], "  ", "pick a choice or write an answer"),
        (["Pink"], "", "that is not one of the question's choices"),
        (["Blue", "Red"], "", "pick one choice"),
    ],
)
def test_a_reply_names_offered_choices_or_says_something(
    choices: list[str], answer: str, refusal: str | None
) -> None:
    question = {"choices": [{"text": "Blue"}, {"text": "Red"}], "several": False}
    assert bad_reply(question, choices, answer) == refusal
