"""The roster rules: the refusal sentences and their order are those of the previous
implementation's roster (`roster.rs`, its `agent_definitions` server tests); the runtimes are
claude and codex only (owner decision of 2026-11-23)."""

from datetime import UTC, datetime, timedelta

import pytest

from code_factory.agents.models.agents import AgentChange, AgentDefinition
from code_factory.agents.rules.roster import apply_change, blank, setup_for, takes
from code_factory.platform.errors import BadRequestError

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def agent(**fields: object) -> AgentDefinition:
    return AgentDefinition.model_validate({"name": "a", "runtime": "claude", **fields})


def change(**fields: object) -> AgentChange:
    return AgentChange.model_validate(fields)


def refusal(base: AgentDefinition, **fields: object) -> str:
    with pytest.raises(BadRequestError) as caught:
        apply_change(base, change(**fields), NOW)
    return str(caught.value)


@pytest.mark.parametrize("name", ["a", "A-b_c.1", "x" * 40, "9"])
def test_a_name_of_letters_digits_and_dash_underscore_dot_is_taken(name: str) -> None:
    assert apply_change(blank(), change(name=name), NOW).name == name


@pytest.mark.parametrize("name", ["", "x" * 41, "-a", ".a", "a b", "a/b", "é"])
def test_other_names_are_refused_in_the_boards_words(name: str) -> None:
    assert refusal(blank(), name=name) == (
        "a name is 1 to 40 letters, digits, '-', '_' or '.', starting with a letter or digit"
    )


def test_an_unknown_runtime_lists_the_two_that_exist() -> None:
    assert refusal(agent(), runtime="other") == "unknown runtime other: claude or codex"


def test_an_unknown_column_lists_the_three_an_agent_works() -> None:
    assert refusal(agent(), roles=["x"]) == ("unknown column x: an agent works spec, build, review")


def test_an_unknown_ticket_type_lists_the_six() -> None:
    assert refusal(agent(), types=["x"]) == (
        "unknown ticket type x: an agent takes feature, bug, refactor, upgrade, hotfix, docs"
    )


@pytest.mark.parametrize("label", ["", "  ", "a,b"])
def test_a_blank_label_or_one_with_a_comma_is_refused(label: str) -> None:
    assert refusal(agent(), labels=[label]) == "a label is a word without a comma"


@pytest.mark.parametrize("model", ["-x", "two words", "a\tb"])
def test_a_model_is_one_word_not_starting_with_a_dash(model: str) -> None:
    assert refusal(agent(), model=model) == "a model is one word, not starting with -"


@pytest.mark.parametrize("field", ["max_tokens", "max_seconds"])
def test_a_limit_of_zero_is_refused_and_one_is_taken(field: str) -> None:
    assert refusal(agent(), **{field: 0}) == "a limit is a whole number above 0"
    assert getattr(apply_change(agent(), change(**{field: 1}), NOW), field) == 1


def test_a_limit_set_to_null_is_cleared_and_one_left_out_is_kept() -> None:
    base = agent(max_tokens=5, max_seconds=6)
    cleared = apply_change(base, change(max_tokens=None), NOW)
    assert (cleared.max_tokens, cleared.max_seconds) == (None, 6)


PRICE = (
    "a price is input_price and output_price together, each dollars per million tokens, 0 or more"
)


def test_prices_come_together_and_zero_is_a_price() -> None:
    assert refusal(agent(), input_price=1.0) == PRICE
    both = apply_change(agent(), change(input_price=0, output_price=0), NOW)
    assert (both.input_price, both.output_price) == (0.0, 0.0)


@pytest.mark.parametrize("price", [-0.01, float("nan"), float("inf"), "1"])
def test_a_negative_infinite_or_non_numeric_price_is_refused(price: object) -> None:
    assert refusal(agent(), input_price=price, output_price=1) == PRICE


def test_a_daily_cap_above_zero_is_taken_and_zero_is_refused() -> None:
    assert apply_change(agent(), change(max_daily_usd=0.01), NOW).max_daily_usd == 0.01
    assert refusal(agent(), max_daily_usd=0) == "a daily cap is dollars above 0"


def test_the_first_refusal_in_the_order_of_the_checks_wins() -> None:
    assert refusal(agent(), name="-", runtime="x", model="-m").startswith("a name is")
    assert refusal(agent(), runtime="x", roles=["y"]).startswith("unknown runtime")


def test_columns_and_types_come_out_in_canonical_order_once_each() -> None:
    made = apply_change(
        agent(), change(roles=["review", "spec", "review"], types=["docs", "bug", "docs"]), NOW
    )
    assert (made.roles, made.types) == (["spec", "review"], ["bug", "docs"])


def test_pausing_sets_the_time_once_and_resuming_clears_it() -> None:
    paused = apply_change(agent(), change(paused=True), NOW)
    assert paused.paused_at == NOW
    again = apply_change(paused, change(paused=True), NOW + timedelta(hours=1))
    assert again.paused_at == NOW
    assert apply_change(again, change(paused=False), NOW).paused_at is None
    assert apply_change(again, change(model="m"), NOW).paused_at == NOW


def test_a_context_over_8000_characters_is_refused_before_anything_else() -> None:
    assert refusal(agent(), context="x" * 9001, name="-") == (
        "context is 9,001 characters; an agent's context holds at most 8,000"
    )
    assert apply_change(agent(), change(context="x" * 8000), NOW).context == "x" * 8000


@pytest.mark.parametrize(
    ("types", "labels", "kind", "csv", "expected"),
    [
        ([], [], "bug", "", True),
        (["bug"], [], "bug", "", True),
        (["bug"], [], "feature", "", False),
        ([], ["ui"], "bug", "ui, api", True),
        ([], ["ui"], "bug", "api, ui", True),
        ([], ["ui"], "bug", "api ,\tui ", True),
        ([], ["ui"], "bug", "api", False),
        ([], ["ui"], "bug", "", False),
        (["bug"], ["ui"], "bug", "ui", True),
        (["bug"], ["ui"], "feature", "ui", False),
        (["bug"], ["ui"], "bug", "api", False),
    ],
)
def test_an_agent_takes_a_ticket_when_each_list_that_is_set_matches(
    types: list[str], labels: list[str], kind: str, csv: str, expected: bool
) -> None:
    assert takes(agent(types=types, labels=labels), kind, csv) is expected


def test_a_stand_in_command_beats_every_template_and_the_agents_runtime_beats_the_repositorys() -> (
    None
):
    worker = agent(runtime="codex", model="m-9")
    assert setup_for(worker, "echo {prompt}", "repo {prompt}", "repo-model") == (
        "echo {prompt}",
        "m-9",
    )
    assert setup_for(worker, "", "repo {prompt}", "repo-model") == ("codex exec", "m-9")
    assert setup_for(agent(), "", "repo {prompt}", "repo-model")[0].startswith("claude -p {prompt}")
    assert setup_for(agent(), "", "repo {prompt}", "repo-model")[1] == "repo-model"
    assert setup_for(None, "", "repo {prompt}", "repo-model") == ("repo {prompt}", "repo-model")


NUL_SENTENCE = "a value cannot hold a NUL character"
INT64_MAX = 2**63 - 1


@pytest.mark.parametrize("field", ["context", "model"])
def test_text_with_a_nul_character_is_refused_in_the_boards_words(field: str) -> None:
    assert refusal(agent(), **{field: "a\x00b"}) == NUL_SENTENCE
    assert getattr(apply_change(agent(), change(**{field: "ab"}), NOW), field) == "ab"


def test_a_label_with_a_nul_character_is_refused() -> None:
    assert refusal(agent(), labels=["x\x00"]) == NUL_SENTENCE


@pytest.mark.parametrize("field", ["max_tokens", "max_seconds"])
def test_a_limit_above_what_the_database_holds_is_refused_and_the_largest_is_taken(
    field: str,
) -> None:
    assert refusal(agent(), **{field: INT64_MAX + 1}) == (
        "a limit is a whole number above 0 and at most 9,223,372,036,854,775,807"
    )
    assert getattr(apply_change(agent(), change(**{field: INT64_MAX}), NOW), field) == INT64_MAX
