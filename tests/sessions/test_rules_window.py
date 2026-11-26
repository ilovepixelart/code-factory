import random

import pytest
from sessions_values import events_by_session, noisy, sample_events

from code_factory.sessions.models import Event
from code_factory.sessions.rules import derive


def in_batches(events: list[Event], rng: random.Random) -> derive.SessionView | None:
    window: list[Event] = []
    carried = ("", "")
    view = None
    at = 0
    while at < len(events):
        size = rng.choice([1, 2, 3, 7, 25])
        window, carried = derive.extend_window(window, carried, events[at : at + size])
        view = derive.derive_unsettled(window, carried)
        assert view is not None
        carried = (view.cwd, view.transcript)
        at += size
    return view


@pytest.mark.parametrize("seed", range(60))
def test_deriving_in_batches_from_a_window_gives_what_deriving_everything_gives(
    seed: int,
) -> None:
    events = noisy(seed, 80)
    assert in_batches(events, random.Random(seed)) == derive.derive_unsettled(events)  # noqa: S311


def test_the_sample_sessions_derived_in_batches_equal_deriving_them_whole() -> None:
    for events in events_by_session(sample_events()).values():
        assert in_batches(events, random.Random(7)) == derive.derive_unsettled(events)  # noqa: S311


def test_a_new_window_starts_at_its_latest_session_start_and_carries_what_came_before() -> None:
    events = noisy(3, 40)
    starts = [e.seq for e in events if e.event == "SessionStart"]
    window, carried = derive.extend_window([], ("", ""), events)
    assert window[0].seq == starts[-1]
    before = events[: starts[-1] - 1]
    expected = derive.carry(("", ""), before)
    assert carried == expected


def test_with_no_session_start_the_window_grows_and_nothing_is_dropped() -> None:
    events = [e for e in noisy(5, 30) if e.event != "SessionStart"]
    window, _ = derive.extend_window(events[:10], ("/a", "/t"), events[10:])
    assert [e.seq for e in window] == [e.seq for e in events]
