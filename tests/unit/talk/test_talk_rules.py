"""The talk rules against hand-worked cases and the previous implementation's sentences.

Sentences, limits and the golden comment texts come from the inbox spec and the previous
implementation's question, message and news tests.
"""

from datetime import UTC, datetime

import pytest

from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.talk.models import Choice, NewsEntry, Question
from code_factory.talk.rules import (
    answer_target,
    check_question,
    check_reply,
    check_topic,
    comment_text,
    fitting,
    message_text,
    news_lines,
    one_line,
    reply_gap,
    route_message,
    ticket_number,
)

WHEN = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)


def ask(
    text: str = "Which colour?", *choices: str, several: bool = False
) -> tuple[str, list[Choice]]:
    return check_question(text, [Choice(text=c) for c in choices], several=several)


def question(*choices: str, several: bool = False, **fields: object) -> Question:
    values: dict[str, object] = {
        "id": 1,
        "ticket_id": "CF-1",
        "document": "spec",
        "index": 0,
        "text": "Which colour?",
        "several": several,
        "choices": [Choice(text=c) for c in choices],
        "asked_by": "run-1",
        "run_id": "",
        "created_at": WHEN,
        "status": "open",
        **fields,
    }
    return Question.model_validate(values)


# check_question


def test_a_question_of_1000_characters_is_taken_and_of_1001_refused() -> None:
    assert len(ask("q" * 1000)[0]) == 1000
    with pytest.raises(BadRequestError, match=r"a question is at most 1000 characters"):
        ask("q" * 1001)


def test_a_question_is_stripped_and_a_blank_one_needs_words() -> None:
    assert ask("  Which colour?  ")[0] == "Which colour?"
    with pytest.raises(BadRequestError, match=r"^a question needs words$"):
        ask("   \n ")


def test_a_question_offers_no_choice_or_two_to_four() -> None:
    assert [len(ask("q", *"ab")[1]), len(ask("q", *"abcd")[1]), len(ask("q")[1])] == [2, 4, 0]
    with pytest.raises(BadRequestError, match=r"^a question offers at most 4 choices$"):
        ask("q", *"abcde")
    with pytest.raises(BadRequestError, match=r"^a question offers no choice or 2 to 4; "):
        ask("q", "a")


def test_the_recommended_choice_comes_first() -> None:
    offered = [Choice(text="a"), Choice(text="b", recommended=True), Choice(text="c")]

    assert [c.text for c in check_question("q", offered, several=False)[1]] == ["b", "a", "c"]


def test_a_choice_keeps_its_description_and_preview_within_their_limits() -> None:
    long = Choice(text="a", description="d" * 501)
    shown = Choice(text="a", description=" Cheaper. ", preview="x = 1\n  y = 2  \n")
    [kept, _] = check_question("q", [shown, Choice(text="b")], several=False)[1]

    assert (kept.description, kept.preview) == ("Cheaper.", "x = 1\n  y = 2")
    given = [long, Choice(text="b")]
    with pytest.raises(BadRequestError, match=r"^a choice's description is at most 500 "):
        check_question("q", given, several=False)
    given = [Choice(text="a", preview="p" * 4001), Choice(text="b")]
    with pytest.raises(BadRequestError, match=r"^a choice's preview is at most 4000 "):
        check_question("q", given, several=False)


def test_a_topic_is_a_one_line_label_of_twelve_characters_at_most() -> None:
    assert check_topic("  Auth method ") == "Auth method"
    assert check_topic("") == ""
    with pytest.raises(BadRequestError, match=r"^a topic is at most 12 characters"):
        check_topic("Authentication")
    with pytest.raises(BadRequestError, match=r"^a topic holds a line break$"):
        check_topic("Auth\nmethod")


def test_choices_are_stripped_and_must_be_one_line_unique_and_up_to_200_characters() -> None:
    assert [c.text for c in ask("q", " blue ", "red")[1]] == ["blue", "red"]
    with pytest.raises(BadRequestError, match=r"^a choice holds a line break$"):
        ask("q", "blue\nred", "x")
    with pytest.raises(BadRequestError, match=r"^a choice is offered twice: blue$"):
        ask("q", "blue", " blue")
    with pytest.raises(BadRequestError, match=r"^a choice needs words$"):
        ask("q", "  ", "x")
    assert len(ask("q", "c" * 200, "x")[1][0].text) == 200
    with pytest.raises(BadRequestError, match=r"^a choice is at most 200 characters$"):
        ask("q", "c" * 201, "x")


def test_two_recommended_choices_need_several() -> None:
    both = [Choice(text="a", recommended=True), Choice(text="b", recommended=True)]
    assert len(check_question("q", both, several=True)[1]) == 2
    with pytest.raises(BadRequestError, match=r"^only one choice is recommended here$"):
        check_question("q", both, several=False)


# check_reply


def test_free_text_is_kept_on_one_line() -> None:
    assert check_reply(question(), [], "  blue   or\tgreen ") == ("blue or green", [])


def test_text_with_a_line_break_is_refused_only_when_choices_are_offered() -> None:
    assert check_reply(question(), [], "a\nb") == ("a b", [])
    given = question("a", "b")
    with pytest.raises(BadRequestError, match=r"^the answer holds a line break$"):
        check_reply(given, [], "a\nb")


def test_picks_come_back_in_the_questions_order_joined_by_commas() -> None:
    got = check_reply(question("red", "green", "blue", several=True), ["blue", "red"], "")
    assert got == ("red, blue", ["red", "blue"])


def test_a_pick_not_offered_names_the_choices_or_says_it_offers_none() -> None:
    given = question("red", "green")
    with pytest.raises(BadRequestError, match=r"^pink is not one of its choices: red, green$"):
        check_reply(given, ["pink"], "")
    given = question()
    with pytest.raises(BadRequestError, match=r"^pink is not one of its choices: it offers none$"):
        check_reply(given, ["pink"], "")


def test_two_picks_on_a_one_pick_question_are_refused() -> None:
    given = question("red", "green")
    with pytest.raises(BadRequestError, match=r"^one choice is picked here$"):
        check_reply(given, ["red", "green"], "")


def test_neither_picks_nor_text_is_refused() -> None:
    given = question("red")
    with pytest.raises(BadRequestError, match=r"^an answer and a question are needed$"):
        check_reply(given, [], "  ")


def test_a_pick_with_a_line_break_is_refused() -> None:
    given = question("red")
    with pytest.raises(BadRequestError, match=r"^a choice holds a line break$"):
        check_reply(given, ["red\n"], "")


# reply_gap: the reply link's pre-check


def test_the_reply_links_pre_check_words() -> None:
    assert reply_gap(question("a", "b"), [], "") == "pick a choice or write an answer"
    assert reply_gap(question("a", "b"), ["c"], "") == "that is not one of the question's choices"
    assert reply_gap(question("a", "b"), ["a", "b"], "") == "pick one choice"
    assert reply_gap(question("a", "b", several=True), ["a", "b"], "") is None
    assert reply_gap(question(), [], "free") is None


def test_the_pre_check_refuses_what_the_full_check_refuses() -> None:
    assert reply_gap(question("a"), [], "x\ny") == "the answer holds a line break"
    assert reply_gap(question("a"), ["a\n"], "") == "a choice holds a line break"


# answer_target


def test_the_shown_text_is_compared_after_stripping_both() -> None:
    questions = [question(id=5, text=" Which colour? "), question(id=6, index=1, text="Size?")]
    assert answer_target(questions, "spec", 0, "  Which colour?").id == 5


def test_a_changed_question_is_a_conflict_naming_what_it_asks_now() -> None:
    given = [question()]
    with pytest.raises(ConflictError, match=r"^the question changed: it now asks Which colour\?$"):
        answer_target(given, "spec", 0, "Which size?")


def test_an_empty_shown_text_and_an_unknown_position_are_refused() -> None:
    given = [question()]
    with pytest.raises(BadRequestError, match=r"^the text of the question answered is needed$"):
        answer_target(given, "spec", 0, "  ")
    given = [question()]
    with pytest.raises(NotFoundError, match=r"^no question 3 in spec$"):
        answer_target(given, "spec", 3, "Which colour?")
    given = [question()]
    with pytest.raises(NotFoundError, match=r"^no question 0 in uat$"):
        answer_target(given, "uat", 0, "Which colour?")


# shapes


def test_the_inbox_shape_is_document_index_text_topic_choices_several() -> None:
    shown = question("blue", document="spec").shown()
    assert shown == {
        "document": "spec.md",
        "index": 0,
        "text": "Which colour?",
        "topic": "",
        "choices": [
            {"text": "blue", "recommended": False, "reason": "", "description": "", "preview": "",
             "ticked": False},
        ],
        "several": False,
    }  # fmt: skip


def test_a_question_without_a_document_shows_an_empty_one() -> None:
    assert question(document="").shown()["document"] == ""


def test_the_ticket_page_shape_adds_the_answer_and_its_channel_and_ticks_the_picks() -> None:
    from code_factory.talk.models import Answer  # noqa: PLC0415

    answered = question("red", "blue", status="answered").model_copy(
        update={
            "answer": Answer(
                id=1, text="blue", picked=["blue"], by="owner", channel="reply", created_at=WHEN
            )
        }
    )
    shown = answered.on_ticket()
    assert list(shown) == [
        "document",
        "index",
        "text",
        "topic",
        "choices",
        "several",
        "answer",
        "answered_by",
    ]
    assert shown["answer"] == "blue"
    assert shown["answered_by"] == "reply"
    assert [c["ticked"] for c in shown["choices"]] == [False, True]
    unanswered = question().on_ticket()
    assert (unanswered["answer"], unanswered["answered_by"]) == ("", "")


# comments, messages, routing


def test_a_comment_carries_its_location_when_it_has_a_path() -> None:
    assert comment_text(" Rename this ", "src/a.py", 12) == "src/a.py:12: Rename this"
    assert comment_text("Looks good", None, None) == "Looks good"
    assert comment_text("Looks good", "", 7) == "Looks good"
    assert comment_text("Look", "src/a.py", None) == "src/a.py: Look"


def test_an_empty_comment_or_message_says_nothing() -> None:
    with pytest.raises(BadRequestError, match=r"^an empty comment says nothing$"):
        comment_text("  ", "a.py", 1)
    with pytest.raises(BadRequestError, match=r"^an empty message says nothing$"):
        message_text(" \n")
    assert message_text("  use files ") == "use files"


@pytest.mark.parametrize(
    ("runtime", "running", "route"),
    [
        ("codex", True, "run"),
        ("claude", True, "run"),
        ("codex", False, "next_run"),
        ("claude", False, "next_run"),
    ],
)
def test_a_message_goes_to_a_running_run_else_waits_for_the_next(
    runtime: str, running: bool, route: str
) -> None:
    assert route_message(runtime, running=running) == route


def test_a_run_whose_runtime_takes_no_input_while_it_works_keeps_the_message_for_the_next() -> None:
    assert route_message("other", running=True) == "next_run"


# news


def test_news_is_one_fact_per_line_in_the_given_order() -> None:
    entries = [
        NewsEntry(kind="answer", text="blue", question="Which colour?"),
        NewsEntry(kind="message", text="use files", message_id=4),
        NewsEntry(kind="comment", text="src/a.py:12: Rename this", author="owner"),
    ]
    text, whole = news_lines(entries, "CF-1")
    assert text.split("\n") == [
        'The owner answered "Which colour?" on CF-1: blue',
        (
            "A message from the owner on CF-1, sent while you work. Take it as the owner's "
            "instruction: use files"
        ),
        "owner commented on CF-1: src/a.py:12: Rename this",
    ]
    assert whole == [4]


def test_news_cut_at_the_limit_keeps_only_whole_messages() -> None:
    first = 'The owner answered "Q" on CF-1: a'
    message = NewsEntry(kind="message", text="x" * 20, message_id=9)
    entries = [NewsEntry(kind="answer", text="a", question="Q"), message]
    fact = (
        "A message from the owner on CF-1, sent while you work. Take it as the owner's "
        "instruction: " + "x" * 20
    )
    whole_length = len(first) + 1 + len(fact)
    text, ids = news_lines(entries, "CF-1", limit=whole_length)
    assert (len(text), ids) == (whole_length, [9])
    text, ids = news_lines(entries, "CF-1", limit=whole_length - 1)
    assert (text, ids) == (first, [])


def test_a_first_entry_too_long_alone_is_given_cut_and_is_not_a_whole_message() -> None:
    message = NewsEntry(kind="message", text="x" * 50, message_id=9)
    text, ids = news_lines([message], "CF-1", limit=30)
    assert (len(text), ids) == (30, [])


def test_the_whole_entries_that_fit_are_counted_for_the_marks() -> None:
    entries = [
        NewsEntry(kind="comment", text="a" * 10, author="o"),
        NewsEntry(kind="comment", text="b" * 10, author="o"),
    ]
    first = len(news_lines(entries[:1], "CF-1")[0])
    assert fitting(entries, "CF-1", limit=first) == 1
    assert fitting(entries, "CF-1", limit=first * 2 + 1) == 2
    assert fitting(entries, "CF-1", limit=3) == 1  # an entry too long alone is still consumed
    assert fitting([], "CF-1", limit=3) == 0


def test_no_news_is_empty() -> None:
    assert news_lines([], "CF-1") == ("", [])


# ids and one_line


def test_a_ticket_id_is_cf_and_a_number_from_one() -> None:
    assert ticket_number("CF-12") == 12
    for bad in ("CF-0", "12", "CF-x", "cf-1", "CF-1.5"):
        with pytest.raises(BadRequestError, match=r"is not a ticket id CF-<n>"):
            ticket_number(bad)


def test_one_line_joins_the_words_with_single_spaces() -> None:
    assert one_line("a \n b\t\tc") == "a b c"
