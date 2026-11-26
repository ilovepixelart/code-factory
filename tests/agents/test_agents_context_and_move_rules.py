"""Context versions, moves in a column and the rename refusal, worked by hand."""

from datetime import UTC, datetime, timedelta

import pytest

from code_factory.agents.models.agents import AgentDefinition
from code_factory.agents.rules.contexts import restore, with_context
from code_factory.agents.rules.roster import move, rename_refusal
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError

T0 = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def bare() -> AgentDefinition:
    return AgentDefinition(name="a", runtime="claude")


def test_a_context_is_set_with_the_time_and_no_version() -> None:
    made = with_context(bare(), "one", T0)
    assert (made.context, made.context_at, made.context_history) == ("one", T0, [])


def test_the_same_text_changes_nothing() -> None:
    made = with_context(bare(), "one", T0)
    assert with_context(made, "one", at(5)) == made


def test_a_new_text_keeps_the_replaced_one_as_the_newest_version() -> None:
    made = with_context(with_context(bare(), "one", at(0)), "two", at(5))
    assert made.context == "two"
    assert [(v.at, v.context) for v in made.context_history] == [(at(0), "one")]
    third = with_context(made, "three", at(9))
    assert [v.context for v in third.context_history] == ["two", "one"]


def test_blank_text_clears_the_context_and_keeps_it_as_a_version() -> None:
    cleared = with_context(with_context(bare(), "one", at(0)), "  \n", at(5))
    assert (cleared.context, cleared.context_at) == (None, None)
    assert [v.context for v in cleared.context_history] == ["one"]


def test_twenty_versions_are_kept_and_the_oldest_goes_on_the_21st_change() -> None:
    made = bare()
    for step in range(22):  # 22 texts: 21 replaced, 20 kept
        made = with_context(made, f"text {step}", at(step))
    assert len(made.context_history) == 20
    assert made.context_history[0].context == "text 20"
    assert made.context_history[-1].context == "text 1"


def test_8000_characters_are_taken_and_8001_refused() -> None:
    assert with_context(bare(), "x" * 8000, T0).context == "x" * 8000
    with pytest.raises(BadRequestError, match=r"context is 8,001 characters"):
        with_context(bare(), "x" * 8001, T0)


def test_a_restored_version_becomes_current_under_its_own_time() -> None:
    made = with_context(with_context(bare(), "one", at(0)), "two", at(5))
    back = restore(made, int(at(0).timestamp()))
    assert (back.context, back.context_at) == ("one", at(0))
    assert [(v.at, v.context) for v in back.context_history] == [(at(5), "two")]


def test_restoring_an_unknown_time_says_so() -> None:
    with pytest.raises(NotFoundError) as caught:
        restore(with_context(bare(), "one", at(0)), 5)
    assert str(caught.value) == "a has no context version of 5"


def roster() -> list[AgentDefinition]:
    return [
        AgentDefinition(name="a", runtime="claude", roles=["build"]),
        AgentDefinition(name="b", runtime="claude", roles=["spec"]),
        AgentDefinition(name="c", runtime="claude", roles=["build", "spec"]),
        AgentDefinition(name="d", runtime="claude", roles=["build"]),
    ]


def names(agents: list[AgentDefinition]) -> str:
    return "".join(agent.name for agent in agents)


def test_up_swaps_with_the_nearest_agent_above_in_the_column_and_others_keep_their_places() -> None:
    assert names(move(roster(), "c", "build", up=True)) == "cabd"
    assert names(move(roster(), "d", "build", up=True)) == "abdc"


def test_down_swaps_with_the_nearest_agent_below_in_the_column() -> None:
    assert names(move(roster(), "a", "build", up=False)) == "bcad"
    assert names(move(roster(), "b", "spec", up=False)) == "acbd"


def test_the_first_cannot_go_up_and_the_last_cannot_go_down() -> None:
    with pytest.raises(ConflictError) as first:
        move(roster(), "a", "build", up=True)
    assert str(first.value) == "a is already first in build"
    with pytest.raises(ConflictError) as last:
        move(roster(), "d", "build", up=False)
    assert str(last.value) == "d is already last in build"


def test_an_agent_not_in_the_column_or_unknown_is_refused() -> None:
    with pytest.raises(BadRequestError) as other:
        move(roster(), "b", "build", up=True)
    assert str(other.value) == "b does not work build"
    with pytest.raises(NotFoundError) as unknown:
        move(roster(), "z", "build", up=True)
    assert str(unknown.value) == "no such agent"


@pytest.mark.parametrize(
    ("held", "expected"),
    [
        (
            ["holds a claim on CF-3"],
            "x holds a claim on CF-3, so it cannot be renamed; add a new agent named y instead",
        ),
        (
            ["holds a claim on CF-3", "has 2 runs"],
            (
                "x holds a claim on CF-3 and has 2 runs, so it cannot be renamed; "
                "add a new agent named y instead"
            ),
        ),
        (
            ["a", "b", "c"],
            "x a, b and c, so it cannot be renamed; add a new agent named y instead",
        ),
    ],
)
def test_a_rename_refusal_joins_what_is_held(held: list[str], expected: str) -> None:
    assert rename_refusal("x", "y", held) == expected


def test_a_rename_with_nothing_held_is_free() -> None:
    assert rename_refusal("x", "y", []) is None


def test_a_restore_takes_the_newest_of_versions_sharing_one_second() -> None:
    made = with_context(bare(), "A", at(0))
    for text in ("B", "C", "D"):
        made = with_context(made, text, at(60))
    assert [(v.context, v.at) for v in made.context_history] == [
        ("C", at(60)),
        ("B", at(60)),
        ("A", at(0)),
    ]
    back = restore(made, int(at(60).timestamp()))
    assert back.context == "C"
