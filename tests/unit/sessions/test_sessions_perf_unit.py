"""The Sessions page and the ingest at the sizes the spec names."""

import json
import statistics
import time

from code_factory.sessions.rules import derive
from sessions_values import noisy

# The design target is 0.3 s and the page took about 0.1 s measured alone; the suite runs beside
# other workers and coverage, so the test only guards against a change of order of magnitude.
# The spec's target for deriving a window of 5,000 events; the median of several runs, because
# one run beside other workers can be slowed several times over by a scheduler pause.
WINDOW_BUDGET_S = 0.030
WINDOW_EVENTS = 5000


def test_a_window_of_5000_events_derives_within_the_target() -> None:
    window = [
        derive.for_views(event)
        for event in noisy(1, 2 * WINDOW_EVENTS)
        if event.event != "SessionStart"
    ][:WINDOW_EVENTS]
    assert len(window) == WINDOW_EVENTS
    took = []
    for _ in range(7):
        started = time.perf_counter()
        view = derive.derive_unsettled(window, ("", ""))
        took.append(time.perf_counter() - started)
    assert view is not None
    assert statistics.median(took) < WINDOW_BUDGET_S, json.dumps({"seconds": took})
