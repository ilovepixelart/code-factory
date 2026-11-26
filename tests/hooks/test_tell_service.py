"""What a running agent is told after a tool result, and how the board learns it was told."""

import pytest

from code_factory.hooks.models import TellConfirm
from code_factory.hooks.ports import NewsFact
from code_factory.platform.errors import BadRequestError
from hooks_fakes import OWNER_ACTOR, STARTED, Fakes, run_actor

MARKS = TellConfirm(through_post=7, through_answer=2, message_ids=[3])
TOOL_USED = {"session_id": "s-1", "hook_event_name": "PostToolUse"}


def with_news() -> Fakes:
    fakes = Fakes()
    fakes.talk.news = NewsFact(text="owner commented on CF-5: Keep it small", confirm=MARKS)
    return fakes


async def test_news_after_a_tool_result_is_the_hook_text_and_the_marks_to_confirm() -> None:
    fakes = with_news()

    answer = await fakes.service().tell(run_actor(), TOOL_USED)

    assert answer.output == (
        '{"hookSpecificOutput": {"hookEventName": "PostToolUse", '
        '"additionalContext": "owner commented on CF-5: Keep it small"}}'
    )
    assert answer.confirm == MARKS
    assert fakes.talk.peeked == [("CF-5", "s-1", STARTED)]
    assert fakes.talk.confirmed == []


async def test_the_event_that_asked_is_the_event_named_in_the_answer() -> None:
    fakes = with_news()

    answer = await fakes.service().tell(
        run_actor(), {"session_id": "s-1", "hook_event_name": "PostToolUseFailure"}
    )

    assert answer.output is not None
    assert '"hookEventName": "PostToolUseFailure"' in answer.output


@pytest.mark.parametrize(
    "payload",
    [
        {"session_id": "s-1", "hook_event_name": "PreToolUse"},
        {"session_id": "s-1", "hook_event_name": "UserPromptSubmit"},
        {"session_id": "", "hook_event_name": "PostToolUse"},
        {"hook_event_name": "PostToolUse"},
        {"session_id": "s-1"},
        {"session_id": 5, "hook_event_name": "PostToolUse"},
        {},
    ],
)
async def test_an_event_that_is_not_a_tool_result_of_a_session_is_told_nothing(
    payload: dict[str, object],
) -> None:
    fakes = with_news()

    answer = await fakes.service().tell(run_actor(), payload)

    assert (answer.output, answer.confirm) == (None, None)
    assert fakes.talk.peeked == []


@pytest.mark.parametrize(
    "actor",
    [OWNER_ACTOR, run_actor(ticket_id=None), run_actor(run_id=None)],
    ids=["owner", "coordinator run", "no run"],
)
async def test_an_actor_without_a_ticket_and_a_run_is_told_nothing(actor: object) -> None:
    fakes = with_news()

    answer = await fakes.service().tell(actor, TOOL_USED)  # ty: ignore[invalid-argument-type]

    assert (answer.output, answer.confirm) == (None, None)
    assert fakes.talk.peeked == []


async def test_a_run_the_board_does_not_know_is_told_nothing() -> None:
    fakes = with_news()
    fakes.runs.at = None

    answer = await fakes.service().tell(run_actor(), TOOL_USED)

    assert (answer.output, answer.confirm) == (None, None)
    assert fakes.talk.peeked == []


async def test_nothing_new_on_the_ticket_is_nothing_to_print() -> None:
    fakes = Fakes()

    answer = await fakes.service().tell(run_actor(), TOOL_USED)

    assert (answer.output, answer.confirm) == (None, None)
    assert fakes.talk.peeked == [("CF-5", "s-1", STARTED)]


async def test_confirming_marks_the_session_once_with_the_marks_it_was_given() -> None:
    fakes = with_news()

    await fakes.service().confirm_tell(run_actor(), "s-1", MARKS.model_dump())

    assert fakes.talk.confirmed == [("CF-5", "s-1", MARKS)]


@pytest.mark.parametrize(
    "confirm",
    [
        {},
        {"through_post": 1, "through_answer": 1},
        {"through_post": -1, "through_answer": 0, "message_ids": []},
        {"through_post": "1", "through_answer": 0, "message_ids": []},
        {"through_post": 1.5, "through_answer": 0, "message_ids": []},
        {"through_post": True, "through_answer": 0, "message_ids": []},
        {"through_post": 1, "through_answer": 0, "message_ids": "3"},
        {"through_post": 1, "through_answer": 0, "message_ids": ["3"]},
        {"through_post": 1, "through_answer": 0, "message_ids": [None]},
    ],
)
async def test_a_malformed_confirm_is_a_bad_request_and_marks_nothing(
    confirm: dict[str, object],
) -> None:
    fakes = with_news()

    with pytest.raises(BadRequestError, match=r"^confirm is malformed$"):
        await fakes.service().confirm_tell(run_actor(), "s-1", confirm)

    assert fakes.talk.confirmed == []


async def test_a_confirm_for_a_session_with_no_ticket_marks_nothing() -> None:
    fakes = with_news()

    await fakes.service().confirm_tell(OWNER_ACTOR, "s-1", MARKS.model_dump())

    assert fakes.talk.confirmed == []


async def test_a_confirm_with_no_session_is_a_bad_request() -> None:
    fakes = with_news()

    with pytest.raises(BadRequestError, match=r"^confirm is malformed$"):
        await fakes.service().confirm_tell(run_actor(), "", MARKS.model_dump())

    assert fakes.talk.confirmed == []
