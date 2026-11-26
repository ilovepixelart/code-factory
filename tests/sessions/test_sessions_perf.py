"""The Sessions page and the ingest at the sizes the spec names."""

import json
import statistics
import time

from sessions_values import NOW, noisy
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.platform.text import Paging
from code_factory.sessions.rules import derive
from code_factory.sessions.service import SessionService

# The design target is 0.3 s and the page took about 0.1 s measured alone; the suite runs beside
# other workers and coverage, so the test only guards against a change of order of magnitude.
PAGE_BUDGET_S = 1.0
# The spec's target for deriving a window of 5,000 events; the median of several runs, because
# one run beside other workers can be slowed several times over by a scheduler pause.
WINDOW_BUDGET_S = 0.030
WINDOW_EVENTS = 5000


async def test_a_page_with_ended_sessions_at_5000_sessions_answers_within_the_budget(
    sessions: SessionService, db_session: AsyncSession
) -> None:
    await db_session.execute(
        text(
            "insert into session_views (session_id, state, last_event_at, last_seq, window_seq, "
            "cwd, repository, branch, transcript, rules_version, view) "
            "select 's' || g, 'idle', to_timestamp(:at - g), g, g, '/w/r' || (g % 20), "
            "'r' || (g % 20), 'main', '', 1, "
            "jsonb_build_object('session_id', 's' || g, 'cwd', '/w/r' || (g % 20), "
            "'state', 'idle', 'last_event_at', :at - g, 'last_prompt', repeat('x', 300)) "
            "from generate_series(1, 5000) as g"
        ),
        {"at": NOW - 100},
    )
    took = []
    for _ in range(3):
        started = time.perf_counter()
        page = await sessions.list_sessions(Paging(1, 50), ended=True)
        took.append(time.perf_counter() - started)
        assert isinstance(page, dict)
        assert page["total"] == 5000
    assert statistics.median(took) < PAGE_BUDGET_S, json.dumps({"seconds": took})


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
