"""What each agent is doing, how its last run ended, its lanes and chains.

Expected values: the previous implementation's lane and chain cases (a ticket's runs by five
agents, 200 to 20 minutes ago) and the outcome words of the team spec.
"""

from typing import Any

import pytest

from code_factory.team.models import TeamRun
from code_factory.team.rules import chains, doing, lanes, last, outcome
from team_values import NOW, agent, ended, lease, run

HOUR = 3600.0
MINUTE = 60.0


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"exit_code": None}, "running"),
        ({"exit_code": 0}, "finished"),
        ({"exit_code": 0, "uncommitted": True}, "uncommitted"),
        ({"exit_code": 1}, "failed"),
        ({"exit_code": -15}, "stopped"),
        ({"exit_code": 1, "limited_until": NOW + 5}, "usage limit"),
        ({"exit_code": 0, "limited_until": NOW + 5}, "usage limit"),
        ({"exit_code": 0, "tokens": 100}, "finished, over limit"),
        ({"exit_code": 0, "tokens": 100, "uncommitted": True}, "uncommitted, over limit"),
        ({"exit_code": 1, "tokens": 100}, "over limit"),
        ({"exit_code": -15, "tokens": 100}, "over limit"),
        ({"exit_code": 0, "tokens": 99}, "finished"),
    ],
)
def test_a_runs_outcome_is_one_word_of_the_table(fields: dict[str, Any], expected: str) -> None:
    writer = agent("writer", "build", max_tokens=100)
    finished = run("r1", agent="writer", ended_at=NOW - 10, **fields)
    assert outcome(writer, finished, [finished]) == expected


def test_over_a_limit_is_read_at_the_moment_the_run_ended() -> None:
    writer = agent("writer", "build", max_seconds=600)
    exact = ended("r1", agent="writer", seconds=600)
    short = ended("r1", agent="writer", seconds=599)
    later = run("r2", agent="writer", started=NOW + 500)  # starts after `short` ended
    assert outcome(writer, exact, [exact]) == "finished, over limit"
    assert outcome(writer, short, [short, later]) == "finished"


def test_last_is_the_latest_run_by_start_of_each_defined_agent() -> None:
    writer = agent("writer", "spec")
    idle = agent("idle", "build")
    runs = [
        ended("old", agent="writer", started=NOW - 500, seconds=10),
        ended("new", "CF-2", agent="writer", started=NOW - 200, seconds=30, stage="spec"),
        ended("other", agent="stranger", started=NOW - 10),
    ]
    found = last([writer, idle], runs, {})
    assert list(found) == ["writer"]
    result = found["writer"]
    assert (result.run, result.id, result.stage, result.at, result.outcome) == (
        "new",
        "CF-2",
        "spec",
        NOW - 170,
        "finished",
    )


def test_last_says_when_a_running_run_started_and_what_a_limit_and_a_refusal_add() -> None:
    writer = agent("writer", "spec")
    running = run("r1", agent="writer", started=NOW - 40)
    assert last([writer], [running], {})["writer"].at == NOW - 40
    parked = ended(
        "r2",
        agent="writer",
        exit_code=1,
        limited_until=NOW + 600,
        resume_refused="writer waits out a usage limit",
        context_at=7,
    )
    result = last([writer], [parked], {})["writer"]
    assert (result.until, result.refused, result.context_at, result.outcome) == (
        NOW + 600,
        "writer waits out a usage limit",
        7,
        "usage limit",
    )


def test_a_working_agent_is_the_holder_of_a_claim_with_a_fresh_beat_and_its_usage() -> None:
    writer = agent("writer", "build", runtime="codex")
    spent = ended("r0", agent="writer", seconds=30, tokens=12)
    found = doing(
        [writer], {"CF-1": lease("writer", (), beat_ago=59)}, [spent], NOW, {"CF-1": "api"}
    )
    state = found["writer"]
    assert (state.state, state.repository, state.id) == ("working", "api", "CF-1")
    assert state.usage is not None
    assert (state.usage.tokens, state.usage.seconds) == (12, 30)


def test_a_claim_with_a_running_run_and_an_old_beat_is_waiting() -> None:
    writer = agent("writer", "build")
    leases = {"CF-1": lease("writer", ("r1",), beat_ago=60)}
    found = doing([writer], leases, [run("r1", agent="writer")], NOW, {})
    assert found["writer"].state == "waiting"


def test_an_idle_agent_is_absent_and_a_lapsed_claim_holds_nothing() -> None:
    writer = agent("writer", "build")
    leases = {"CF-1": lease("writer", (), beat_ago=60)}
    assert doing([writer, agent("idle", "spec")], leases, [], NOW, {}) == {}


def test_without_a_claim_an_agent_at_a_cap_on_its_latest_ticket_is_over_limit() -> None:
    writer = agent("writer", "build", max_tokens=10)
    spent = ended("r1", "CF-4", agent="writer", tokens=10, repository="api")
    found = doing([writer], {}, [spent], NOW, {})
    assert (found["writer"].state, found["writer"].id, found["writer"].repository) == (
        "over limit",
        "CF-4",
        "api",
    )
    assert found["writer"].usage is None
    within = ended("r1", "CF-4", agent="writer", tokens=9)
    assert doing([writer], {}, [within], NOW, {}) == {}


def _timed(
    id_: str, agent_name: str, ticket: str, start_min: float, end_min: float | None
) -> TeamRun:
    started = NOW - start_min * MINUTE
    if end_min is None:
        return run(id_, ticket, agent_name, started=started, repository="api")
    return ended(
        id_,
        ticket,
        agent_name,
        started=started,
        seconds=(start_min - end_min) * MINUTE,
        repository="api",
    )


def test_lanes_follow_the_roster_then_a_default_lane_and_keep_the_window_edge() -> None:
    writer, builder = agent("writer", "spec"), agent("builder", "build")
    runs = [
        ended("w-old", agent="writer", started=NOW - 8 * HOUR, seconds=HOUR, repository="api"),
        run("b-now", agent="builder", started=NOW - 8 * HOUR, repository="api"),
        ended("w-two", agent="writer", started=NOW - 3 * HOUR, seconds=HOUR, repository="api"),
        ended("w-four", agent="writer", started=NOW - 5 * HOUR, seconds=HOUR, repository="api"),
        ended("d-one", agent="", started=NOW - 2 * HOUR, seconds=HOUR, repository="api"),
        ended("w-edge", agent="writer", started=NOW - 6 * HOUR, seconds=60, repository="api"),
    ]
    held = {"CF-1": lease("builder", ("b-now",), beat_ago=5)}
    result = lanes([writer, builder], runs, held, (NOW - 6 * HOUR, NOW), {"CF-1": "api"})
    assert [(lane.agent, [r.id for r in lane.runs]) for lane in result] == [
        ("writer", ["w-four", "w-two"]),
        ("builder", ["b-now"]),
        ("default", ["d-one"]),
    ]
    assert result[0].doing is None
    assert result[1].doing is not None
    assert result[1].doing.state == "working"
    two = result[0].runs[1]
    assert (two.repository, two.ticket, two.stage, two.started_at, two.outcome) == (
        "api",
        "CF-1",
        "build",
        NOW - 3 * HOUR,
        "finished",
    )
    assert result[1].runs[0].ended_at is None
    assert result[1].runs[0].outcome == "running"


def test_no_agent_and_no_run_make_no_lane() -> None:
    assert lanes([], [], {}, (NOW - 6 * HOUR, NOW), {}) == ()


def test_chains_link_a_tickets_runs_with_the_minutes_waited_between_them() -> None:
    names = ("writer", "builder", "reviewer")
    roster = [agent(name, "build") for name in names]
    runs = [
        _timed("r-review", "reviewer", "CF-1", 69, 50),
        _timed("r-write", "writer", "CF-1", 200, 180),
        _timed("r-again", "builder", "CF-1", 55, 30),
        _timed("r-build", "builder", "CF-1", 176, 100),
        _timed("r-last", "reviewer", "CF-1", 20, None),
        _timed("r-other", "builder", "CF-2", 90, 80),
        ended("r-none", "", "builder", started=NOW - 600, seconds=300),
    ]
    found = chains(lanes(roster, runs, {}, (NOW - 6 * HOUR, NOW), {}))
    assert [(c.repository, c.ticket, c.runs, c.waited) for c in found] == [
        (
            "api",
            "CF-1",
            ("r-write", "r-build", "r-review", "r-again", "r-last"),
            (240.0, 1860.0, 0.0, 600.0),
        ),
        ("api", "CF-2", ("r-other",), ()),
    ]


def test_a_wait_after_a_run_that_still_runs_is_unknown() -> None:
    roster = [agent("a", "build"), agent("b", "build")]
    runs = [_timed("r1", "a", "CF-1", 60, None), _timed("r2", "b", "CF-1", 30, 20)]
    found = chains(lanes(roster, runs, {}, (NOW - 6 * HOUR, NOW), {}))
    assert found[0].waited == (None,)


def test_runs_starting_together_chain_by_their_id() -> None:
    roster = [agent("a", "build")]
    runs = [_timed("rb", "a", "CF-1", 30, 20), _timed("ra", "a", "CF-1", 30, 25)]
    found = chains(lanes(roster, runs, {}, (NOW - 6 * HOUR, NOW), {}))
    assert found[0].runs == ("ra", "rb")
    assert found[0].waited == (0.0,)
