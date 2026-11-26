"""Claim rules; expected values are the hand-worked cases of the team spec."""

import pytest

from code_factory.team.rules import ClaimHeld, busy, claim, holds, kept, who
from team_values import NOW, ended, lease, run


def test_a_claim_holds_while_a_run_of_it_is_active_however_old_its_beat() -> None:
    assert holds(lease("writer", ("r1",), beat_ago=120), [run("r1")], NOW)


def test_a_claim_whose_only_run_ended_does_not_hold_with_a_fresh_beat() -> None:
    assert not holds(lease("writer", ("r1",), beat_ago=1), [ended("r1")], NOW)


@pytest.mark.parametrize(("beat_ago", "expected"), [(59.9, True), (60.0, False)])
def test_a_claim_with_no_recorded_run_holds_until_its_beat_is_60_seconds_old(
    beat_ago: float, expected: bool
) -> None:
    assert holds(lease("writer", (), beat_ago), [], NOW) is expected


def test_a_run_id_the_runs_do_not_record_counts_as_no_run_recorded() -> None:
    assert holds(lease("writer", ("lost",), beat_ago=59), [run("other")], NOW)
    assert not holds(lease("writer", ("lost",), beat_ago=61), [run("other")], NOW)


def test_the_default_agent_is_named_as_such() -> None:
    assert who("") == "the default agent"
    assert who("writer") == "writer"


def test_a_held_claim_refuses_a_second_naming_its_holder() -> None:
    given = {"CF-1": lease("writer", ("r1",), beat_ago=120)}
    given_2 = [run("r1")]
    with pytest.raises(ClaimHeld, match=r"^writer holds this ticket$"):
        claim(given, "CF-1", "coder", given_2, NOW)


def test_a_held_default_agent_claim_is_named_the_default_agent() -> None:
    given = {"CF-1": lease("", (), beat_ago=59)}
    with pytest.raises(ClaimHeld, match=r"^the default agent holds this ticket$"):
        claim(given, "CF-1", "coder", [], NOW)


def test_a_claim_is_free_once_its_run_ended_and_the_new_one_starts_now() -> None:
    fresh = claim({"CF-1": lease("writer", ("r1",))}, "CF-1", "coder", [ended("r1")], NOW)
    assert (fresh.agent, fresh.runs, fresh.claimed_at, fresh.beat_at) == ("coder", (), NOW, NOW)


def test_a_claim_on_another_ticket_is_not_blocked() -> None:
    assert claim({"CF-1": lease("writer", (), 1)}, "CF-2", "writer", [], NOW).agent == "writer"


def test_kept_beats_a_claim_with_an_active_run_and_drops_what_no_longer_holds() -> None:
    leases = {
        "CF-1": lease("writer", ("r1",), beat_ago=90),
        "CF-2": lease("scribe", ("r2",), beat_ago=2),
        "CF-3": lease("coder", (), beat_ago=10),
    }
    result = kept(leases, [run("r1"), ended("r2", "CF-2")], NOW)
    assert set(result) == {"CF-1", "CF-3"}
    assert result["CF-1"].beat_at == NOW
    assert result["CF-1"].claimed_at == NOW - 90
    assert result["CF-3"] == leases["CF-3"]


def test_busy_names_the_defined_agents_with_a_holding_claim() -> None:
    leases = {
        "CF-1": lease("writer", (), 5),
        "CF-2": lease("", (), 5),
        "CF-3": lease("coder", (), 61),
    }
    assert busy(leases, [], NOW) == {"writer": "CF-1"}
