import pytest

from code_factory.platform.errors import BadRequestError
from code_factory.platform.text import Paging
from code_factory.sessions.models import Action, SessionState, SessionView, StateFilter
from code_factory.sessions.rules.page import list_json, page_json, session_json


def view(
    session_id: str, repository: str, state: str, at: float, *, stale: bool = False
) -> SessionView:
    return SessionView(
        session_id=session_id,
        cwd=f"/work/{repository}",
        repository=repository,
        state=SessionState(state),
        last_event_at=at,
        stale=stale,
    )


def ids(answer: dict[str, object], key: str) -> list[str]:
    rows = answer[key]
    assert isinstance(rows, list)
    return [row["session_id"] for row in rows]


# In attention order: blocked, working, idle, ended. beta holds the newest activity of the rest
# (b1 at 90), so its group comes first.
VIEWS = [
    view("w1", "alpha", "blocked", 10.0),
    view("a1", "alpha", "working", 50.0),
    view("b1", "beta", "working", 90.0),
    view("a2", "alpha", "idle", 40.0),
    view("b2", "beta", "idle", 20.0),
    view("a3", "alpha", "ended", 95.0),
]
EVERY_STATE = [
    view("w1", "alpha", "blocked", 10.0),
    view("a1", "alpha", "working", 50.0),
    view("b1", "beta", "working", 90.0),
    view("a2", "alpha", "idle", 40.0),
    view("s1", "beta", "working", 5.0, stale=True),
    view("a3", "alpha", "ended", 95.0),
]


def page(
    number: int, size: int, *, ended: bool = False, state: StateFilter | None = None
) -> dict[str, object]:
    return page_json(VIEWS, 100.0, Paging(number, size), ended=ended, state=state, ended_hidden=1)


def test_waiting_stays_whole_and_the_rest_pages_by_repository() -> None:
    first = page(1, 3)
    assert ids(first, "waiting") == ["w1"]
    assert ids(first, "rows") == ["b1", "b2", "a1"]
    assert [first[key] for key in ("total", "page", "size", "ended_hidden")] == [4, 1, 3, 1]
    second = page(2, 3)
    assert ids(second, "waiting") == ["w1"]
    assert ids(second, "rows") == ["a2"]


def test_ended_sessions_join_the_rest_when_asked() -> None:
    answer = page(1, 10, ended=True)
    # a3's 95 makes alpha's group the newest.
    assert ids(answer, "rows") == ["a1", "a2", "a3", "b1", "b2"]
    assert (answer["total"], answer["ended_hidden"]) == (5, 0)


def test_a_page_past_the_last_is_the_last() -> None:
    answer = page(9, 3)
    assert answer["page"] == 2
    assert ids(answer, "rows") == ["a2"]


def test_the_answer_lists_its_keys_in_the_order_of_the_previous_one() -> None:
    assert list(page(1, 3)) == [
        "waiting", "ended_hidden", "counts", "repositories", "rows", "total", "page", "size",
    ]  # fmt: skip


def filtered(state: StateFilter | None, *, ended: bool = False) -> dict[str, object]:
    return page_json(EVERY_STATE, 100.0, Paging(1, 10), ended=ended, state=state, ended_hidden=0)


def test_a_state_keeps_its_sessions_and_the_counts_stay_whole() -> None:
    counts = {"waiting": 1, "working": 2, "idle": 1, "stale": 1}
    working = filtered(StateFilter.WORKING)
    assert ids(working, "rows") == ["b1", "a1"]
    assert working["total"] == 2
    assert working["counts"] == counts
    assert working["repositories"] == {"beta": 1, "alpha": 1}
    assert ids(working, "waiting") == []
    assert ids(filtered(StateFilter.STALE), "rows") == ["s1"]
    assert ids(filtered(StateFilter.IDLE), "rows") == ["a2"]
    waiting = filtered(StateFilter.WAITING)
    assert (ids(waiting, "waiting"), ids(waiting, "rows")) == (["w1"], [])
    assert waiting["counts"] == counts
    everything = filtered(None)
    assert everything["counts"] == counts
    assert everything["repositories"] == {"beta": 2, "alpha": 2}


def test_an_ended_session_is_under_no_state_and_shows_without_one() -> None:
    everything = filtered(None, ended=True)
    assert everything["counts"] == {"waiting": 1, "working": 2, "idle": 1, "stale": 1}
    assert everything["repositories"] == {"alpha": 3, "beta": 2}
    assert everything["total"] == 5
    assert filtered(StateFilter.IDLE, ended=True)["total"] == 1


@pytest.mark.parametrize("name", ["waiting", "working", "idle", "stale"])
def test_a_state_query_names_one_of_four_states(name: str) -> None:
    assert StateFilter.from_text(name).value == name


@pytest.mark.parametrize("bad", ["", "ended", "Idle", "blocked"])
def test_any_other_state_is_refused_with_the_sentence(bad: str) -> None:
    with pytest.raises(
        BadRequestError, match=r"^state must be one of waiting, working, idle, stale$"
    ):
        StateFilter.from_text(bad)


def test_a_session_with_no_repository_groups_under_unknown_repository() -> None:
    answer = page_json(
        [view("x", "", "working", 1.0)], 2.0, Paging(1, 5), ended=False, state=None, ended_hidden=0
    )
    assert answer["repositories"] == {"unknown repository": 1}


def test_the_list_cuts_text_to_160_characters_and_drops_the_seconds_since_now() -> None:
    long = "é" * 161
    shown = view("s", "r", "working", 1.0).model_copy(
        update={
            "last_prompt": long,
            "current_action": Action(tool="Bash", summary=long, started_at=1.0),
        }
    )
    row = list_json(shown, 9.0)
    assert row["last_prompt"] == "é" * 159 + "…"
    assert "age_seconds" not in row
    assert row["current_action"] == {
        "tool": "Bash",
        "summary": "é" * 159 + "…",
        "started_at": 1.0,
        "tool_use_id": None,
    }
    assert session_json(shown, 9.0)["age_seconds"] == 8.0
    exact = shown.model_copy(update={"last_prompt": "é" * 160})
    assert list_json(exact, 9.0)["last_prompt"] == "é" * 160
