"""The talk's records read as activity lines: who said it and what."""

from datetime import UTC, datetime

import pytest

from code_factory.board.rules.talk import talk_line
from code_factory.talk.models import TalkEntry

AT = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)


def entry(kind: str, by: str = "owner", text: str = "hello") -> TalkEntry:
    return TalkEntry(kind=kind, id=1, ticket_id="CF-1", at=AT, by=by, text=text, data={})  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize(
    ("kind", "sentence"),
    [
        ("question", "You asked"),
        ("answer", "You answered"),
        ("comment", "You commented"),
        ("message", "You sent a message"),
    ],
)
def test_each_kind_of_talk_has_its_sentence(kind: str, sentence: str) -> None:
    assert talk_line(entry(kind)).sentence == sentence


@pytest.mark.parametrize(
    ("by", "sentence"),
    [
        ("owner:owner", "You answered"),
        ("owner:laptop", "You answered"),
        ("run:3f2a9c1b7d4e", "An agent answered"),
        ("run:builder", "An agent answered"),
        ("board", "Board answered"),
    ],
)
def test_the_author_is_named_in_words_not_by_actor_id(by: str, sentence: str) -> None:
    assert talk_line(entry("answer", by=by)).sentence == sentence


def test_the_line_keeps_the_author_id_for_the_page() -> None:
    assert talk_line(entry("question", by="run:builder")).by == "run:builder"


def test_the_line_keeps_the_words_the_moment_and_the_kind() -> None:
    line = talk_line(entry("comment", text="looks right"))
    assert (line.kind, line.at, line.data) == ("comment", AT, {"text": "looks right"})
    assert line.source == "talk"


def test_an_entry_with_no_author_is_said_by_someone() -> None:
    assert talk_line(entry("comment", by="")).sentence == "Someone commented"
