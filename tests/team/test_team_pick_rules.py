"""Which agent takes a ticket, or why none does; sentences and cases from the team spec."""

import pytest

from code_factory.team.models import TeamAgent, TeamRun
from code_factory.team.rules import (
    NoAgent,
    QueueRule,
    Team,
    failed_here,
    passed_over,
    pick,
    unable,
)
from team_values import NOW, agent, ask, ended, run

WRITER = agent("writer", "spec")
SCRIBE = agent("scribe", "spec")
CODER = agent("coder", "build")


def reason(
    agents: list[TeamAgent],
    busy: dict[str, str] | None = None,
    runs: tuple[TeamRun, ...] = (),
    **fields: object,
) -> str:
    """The sentence a refused pick raises."""
    with pytest.raises(NoAgent) as refused:
        pick(agents, busy or {}, ask(*runs, **fields))  # ty: ignore[invalid-argument-type]
    return str(refused.value)


def test_no_agents_defined_leaves_the_ticket_to_the_default_agent() -> None:
    assert pick([], {}, ask()) is None


def test_the_first_agent_of_the_column_takes_the_ticket_then_the_next_when_it_is_busy() -> None:
    assert pick([WRITER, SCRIBE, CODER], {}, ask(stage="spec")) is WRITER
    assert pick([WRITER, SCRIBE, CODER], {"writer": "CF-9"}, ask(stage="spec")) is SCRIBE


def test_an_agent_holding_this_very_ticket_is_not_busy_for_it() -> None:
    assert pick([WRITER, SCRIBE], {"writer": "CF-1"}, ask(stage="spec")) is WRITER


def test_when_every_agent_holds_another_ticket_the_first_is_named_with_its_ticket() -> None:
    busy = {"writer": "CF-8", "scribe": "CF-9"}
    assert reason([WRITER, SCRIBE], busy, stage="spec") == "writer working CF-8"


def test_a_column_nobody_works_is_left_to_the_default_agent() -> None:
    assert pick([CODER], {}, ask(stage="spec")) is None


@pytest.mark.parametrize(
    ("agent_", "kind", "labels", "taken"),
    [
        (agent("a", "build"), "bug", "x", True),
        (agent("a", "build", types=("bug",)), "bug", "", True),
        (agent("a", "build", types=("bug",)), "feature", "", False),
        (agent("a", "build", labels=("api",)), "feature", "web, api", True),
        (agent("a", "build", labels=("api",)), "feature", "web", False),
        (agent("a", "build", labels=("api",)), "feature", "", False),
        (agent("a", "build", types=("bug",), labels=("api",)), "bug", "api", True),
        (agent("a", "build", types=("bug",), labels=("api",)), "feature", "api", False),
        (agent("a", "build", types=("bug",), labels=("api",)), "bug", "web", False),
    ],
)
def test_a_list_limits_only_its_kind_and_both_lists_must_match(
    agent_: TeamAgent, kind: str, labels: str, taken: bool
) -> None:
    ticket = ask(kind=kind, labels=labels)
    if taken:
        assert pick([agent_], {}, ticket) is agent_
    else:
        assert reason([agent_], kind=kind, labels=labels) == (
            "no agent of this column takes this ticket's type and labels"
        )


def test_a_writer_never_reviews_its_own_build() -> None:
    reviewer = agent("rev", "review")
    wrote = ended("r1", agent="rev", stage="build")
    assert reason([reviewer], stage="review", runs=(wrote,)) == (
        "no reviewer that did not write the code"
    )
    other = ended("r1", agent="coder", stage="build")
    assert pick([reviewer], {}, ask(other, stage="review")) is reviewer
    elsewhere = ended("r1", "CF-2", agent="rev", stage="build")
    assert pick([reviewer], {}, ask(elsewhere, stage="review")) is reviewer


def test_a_critique_is_judged_like_a_review() -> None:
    reviewer = agent("rev", "review")
    wrote = ended("r1", agent="rev", stage="build")
    assert reason([reviewer], stage="critique", runs=(wrote,)) == (
        "no reviewer that did not write the code"
    )


def test_a_reader_never_reads_the_documents_it_wrote() -> None:
    wrote = ended("r1", agent="writer", stage="spec")
    assert reason([WRITER], stage="read", runs=(wrote,)) == (
        "no reader that did not write the documents"
    )
    assert pick([WRITER, SCRIBE], {}, ask(wrote, stage="read")) is SCRIBE


def test_the_coder_takes_its_own_ticket_back_in_build() -> None:
    wrote = ended("r1", agent="coder", stage="build")
    assert pick([CODER], {}, ask(wrote, stage="build")) is CODER


def test_the_default_agent_reviews_unless_it_wrote_the_code() -> None:
    by_coder = ended("r1", agent="coder", stage="build")
    by_default = ended("r1", agent="", stage="build")
    assert pick([CODER], {}, ask(by_coder, stage="review")) is None
    assert reason([CODER], stage="review", runs=(by_default,)) == (
        "no reviewer that did not write the code"
    )


def test_another_model_is_asked_of_a_reviewer_by_runtime_connection_or_model() -> None:
    coder = agent("coder", "build", runtime="claude", connection="a", model="m")
    same = agent("same", "review", runtime="claude", connection="a", model="m")
    by_model = agent("by_model", "review", runtime="claude", connection="a", model="n")
    by_connection = agent("by_connection", "review", runtime="claude", connection="b", model="m")
    by_runtime = agent("by_runtime", "review", runtime="codex", connection="a", model="m")
    wrote = ended("r1", agent="coder", stage="build")
    ticket = ask(wrote, stage="review", other_model=True)
    roster = [coder, same, by_model, by_connection, by_runtime]
    assert pick(roster, {}, ticket) is by_model
    assert pick([coder, same], {}, ask(wrote, stage="review", other_model=False)) is same
    with pytest.raises(NoAgent, match=r"^no reviewer on another model than the code's$"):
        pick([coder, same], {}, ticket)


def test_a_writer_without_a_definition_empties_the_other_model_list() -> None:
    reviewer = agent("rev", "review", runtime="codex")
    by_default = ended("r1", agent="", stage="build")
    with pytest.raises(NoAgent, match=r"^no reviewer on another model than the code's$"):
        pick([reviewer], {}, ask(by_default, stage="review", other_model=True))


def test_with_no_reviewer_defined_another_model_cannot_be_promised() -> None:
    wrote = ended("r1", agent="coder", stage="build")
    with pytest.raises(NoAgent, match=r"^no reviewer on another model than the code's$"):
        pick([CODER], {}, ask(wrote, stage="review", other_model=True))
    assert pick([CODER], {}, ask(stage="review", other_model=True)) is None


def test_a_paused_agent_takes_no_new_ticket() -> None:
    paused = agent("qwen", "spec", paused_at=NOW - 5)
    assert pick([paused, SCRIBE], {}, ask(stage="spec")) is SCRIBE
    assert reason([paused], stage="spec") == "qwen paused for Spec"


def test_a_paused_agent_keeps_the_ticket_whose_claim_it_holds() -> None:
    paused = agent("qwen", "spec", paused_at=NOW - 5)
    assert pick([paused], {"qwen": "CF-1"}, ask(stage="spec")) is paused


def test_the_pause_sentence_names_the_first_agent_of_the_column_only() -> None:
    paused = agent("qwen", "spec", paused_at=NOW - 5)
    assert reason([CODER, paused], stage="spec") == "qwen paused for Spec"


def test_an_agent_at_its_cap_on_the_ticket_is_passed_and_the_first_capped_is_named() -> None:
    capped = agent("capped", "build", max_tokens=100)
    free = agent("free", "build")
    spent = ended("r1", agent="capped", tokens=100)
    assert pick([capped, free], {}, ask(spent)) is free
    assert reason([capped], runs=(spent,)) == "capped 100 of 100 tokens"


def test_an_agent_at_its_day_cap_is_passed() -> None:
    capped = agent("capped", "build", max_daily_usd=1.0)
    spent = ended("r1", "CF-7", agent="capped", cost=1.0)
    assert reason([capped], runs=(spent,)) == "capped $1.00 of $1.00 on 2026-11-23"


def test_an_agent_waiting_out_a_usage_limit_is_passed() -> None:
    limited = agent("limited", "build")
    free = agent("free", "build")
    parked = ended("r1", "CF-7", agent="limited", exit_code=1, limited_until=NOW + 600)
    assert pick([limited, free], {}, ask(parked)) is free
    assert reason([limited], runs=(parked,)) == "limited waits out a usage limit"
    over = ended("r1", "CF-7", agent="limited", exit_code=1, limited_until=NOW - 1)
    assert pick([limited, free], {}, ask(over)) is limited
    reset = ended("r1", "CF-7", agent="limited", exit_code=1, limited_until=NOW)
    assert pick([limited, free], {}, ask(reset)) is limited


def test_a_failed_model_check_passes_the_agent_with_its_sentence() -> None:
    sentence = "agent a: m failed its model check (too small); test it again on the Agents page"
    broken = agent("a", "build", refusal=sentence)
    assert reason([broken]) == sentence
    assert pick([broken, CODER], {}, ask()) is CODER


def test_the_first_within_cap_candidates_ability_sentence_is_the_refusal() -> None:
    first = agent("first", "build", refusal="first is broken")
    second = agent("second", "build", refusal="second is broken")
    assert reason([first, second]) == "first is broken"


def test_escalation_passes_an_agent_that_failed_this_stage_here() -> None:
    first = agent("first", "build")
    second = agent("second", "build")
    failed = ended("r1", agent="first", exit_code=1)
    assert pick([first, second], {}, ask(failed, escalate=True)) is second
    assert pick([first, second], {}, ask(failed, escalate=False)) is first


def test_escalation_lifts_when_every_agent_of_the_column_failed_the_stage() -> None:
    first = agent("first", "build")
    second = agent("second", "build")
    runs = (
        ended("r1", agent="first", exit_code=1, started=NOW - 300),
        ended("r2", agent="second", exit_code=1, started=NOW - 200),
    )
    assert pick([first, second], {}, ask(*runs, escalate=True)) is first


def test_a_latest_failure_is_named_with_its_column_and_exit() -> None:
    first = agent("first", "build")
    failed = ended("r1", agent="first", exit_code=3)
    assert failed_here(first, ask(failed)) == "first failed this ticket at Build (exit 3)"
    assert failed_here(first, ask(failed, stage="released")) is None  # no run at that stage


def test_a_stopped_run_a_limit_and_a_later_pass_are_not_failures() -> None:
    first = agent("first", "build")
    stopped = ended("r1", agent="first", exit_code=-15)
    limited = ended("r1", agent="first", exit_code=1, limited_until=NOW + 5)
    failed = ended("r1", agent="first", exit_code=1, started=NOW - 300)
    recovered = ended("r2", agent="second", started=NOW - 100)
    assert failed_here(first, ask(stopped)) is None
    assert failed_here(first, ask(limited)) is None
    assert failed_here(first, ask(failed, recovered)) is None
    assert failed_here(first, ask(run("r1", agent="first"))) is None  # still running


def test_a_pass_that_made_no_progress_is_a_failure_with_its_own_sentence() -> None:
    first = agent("first", "review")
    quiet = ended("r1", agent="first", stage="review", halted="no progress for 10 minutes")
    assert failed_here(first, ask(quiet, stage="review")) == (
        "first made no progress on this ticket at Review"
    )


def test_an_unknown_stage_reads_as_released() -> None:
    first = agent("first", "build")
    failed = ended("r1", agent="first", stage="released", exit_code=1)
    assert failed_here(first, ask(failed, stage="released")) == (
        "first failed this ticket at Released (exit 1)"
    )


def test_unable_orders_a_limit_before_a_failed_check_before_a_failure() -> None:
    first = agent("first", "build", refusal="broken")
    limited = ended("r1", agent="first", exit_code=1, limited_until=NOW + 9)
    assert unable(first, ask(limited, escalate=True)) == "first waits out a usage limit"
    assert unable(first, ask(escalate=True)) == "broken"
    plain = agent("first", "build")
    failed = ended("r1", agent="first", exit_code=2)
    assert unable(plain, ask(failed, escalate=True)) == "first failed this ticket at Build (exit 2)"
    assert unable(plain, ask(failed)) is None


def test_passed_over_names_each_agent_ahead_of_the_one_taken() -> None:
    first = agent("first", "build")
    second = agent("second", "build")
    third = agent("third", "build")
    limited = ended("r1", "CF-7", agent="first", exit_code=1, limited_until=NOW + 9)
    broken = agent("second", "build", refusal="second is broken")
    assert passed_over([first, broken, third], third, ask(limited)) == [
        "first waits out a usage limit, continued by third",
        "second is broken",
    ]
    assert passed_over([first, second, third], first, ask(limited)) == []


def test_passed_over_without_a_taken_agent_names_every_one_unable() -> None:
    broken = agent("a", "build", refusal="a is broken")
    assert passed_over([broken], None, ask()) == ["a is broken"]


def test_the_queue_rule_gives_each_ready_ticket_a_free_agent_of_its_column() -> None:
    rule = QueueRule(Team(agents=(WRITER, SCRIBE, CODER), runs=(), busy={}, now=NOW))
    reasons = [
        rule("CF-1", "spec", "feature", ""),
        rule("CF-2", "spec", "feature", ""),
        rule("CF-3", "spec", "feature", ""),
        rule("CF-4", "build", "feature", ""),
    ]
    assert reasons == ["", "", "writer working CF-1", ""]


def test_the_queue_rule_does_not_change_the_busy_map_it_was_given() -> None:
    busy = {"coder": "CF-9"}
    rule = QueueRule(Team(agents=(WRITER,), runs=(), busy=busy, now=NOW))
    assert rule("CF-1", "spec", "feature", "") == ""
    assert busy == {"coder": "CF-9"}


def test_the_queue_rule_says_no_agent_for_a_column_nobody_works() -> None:
    rule = QueueRule(Team(agents=(CODER,), runs=(), busy={}, now=NOW))
    assert rule("CF-1", "spec", "feature", "") == "no agent for this column"


def test_with_no_agents_the_queue_rule_changes_nothing_and_does_not_park() -> None:
    rule = QueueRule(Team(agents=(), runs=(), busy={}, now=NOW))
    assert rule("CF-1", "spec", "feature", "") == ""
    assert rule.parked is False
    assert QueueRule(Team(agents=(CODER,), runs=(), busy={}, now=NOW)).parked is True


def test_the_queue_rule_gives_the_refusal_sentence_of_a_held_ticket() -> None:
    rule = QueueRule(Team(agents=(agent("a", "build", types=("bug",)),), runs=(), busy={}, now=NOW))
    assert rule("CF-1", "build", "feature", "") == (
        "no agent of this column takes this ticket's type and labels"
    )
