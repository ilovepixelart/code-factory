"""The wire form of an agent is `AgentDefinition.ts` of the previous implementation: its key
order, the keys it omits, whole epoch seconds."""

import math
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from code_factory.agents.models.agents import (
    KEPT,
    AgentChange,
    AgentDefinition,
    ContextVersion,
)

NOON = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)  # 1795435200
LATER = datetime(2026, 11, 23, 12, 5, tzinfo=UTC)  # 1795435500


def test_a_bare_agent_has_only_the_keys_the_app_always_reads() -> None:
    wire = AgentDefinition(name="a", runtime="claude", roles=["build"]).wire()
    assert list(wire) == [
        "name",
        "runtime",
        "connection",
        "model",
        "roles",
        "max_tokens",
        "max_seconds",
    ]
    assert wire["max_tokens"] is None
    assert wire["max_seconds"] is None


def test_a_full_agent_lists_its_keys_in_the_order_of_the_generated_type() -> None:
    agent = AgentDefinition(
        name="a",
        runtime="codex",
        connection="login",
        model="m",
        roles=["spec"],
        types=["bug"],
        labels=["x"],
        max_tokens=10,
        max_seconds=20,
        input_price=1.5,
        output_price=2.5,
        max_daily_usd=3.0,
        paused_at=NOON,
        context="ctx",
        context_at=NOON,
        context_history=[ContextVersion(at=LATER, context="old")],
    )
    wire = agent.wire()
    assert list(wire) == [
        "name",
        "runtime",
        "connection",
        "model",
        "roles",
        "types",
        "labels",
        "max_tokens",
        "max_seconds",
        "input_price",
        "output_price",
        "max_daily_usd",
        "paused_at",
        "context",
        "context_at",
        "context_history",
    ]
    assert wire["paused_at"] == 1795435200
    assert wire["context_at"] == 1795435200
    assert wire["context_history"] == [{"at": 1795435500, "context": "old"}]


def test_an_absent_limit_is_kept_null_clears_and_a_number_sets() -> None:
    assert AgentChange().max_tokens is KEPT
    assert AgentChange.model_validate({"max_tokens": None}).max_tokens is None
    assert AgentChange.model_validate({"max_tokens": 7}).max_tokens == 7


@pytest.mark.parametrize("given", [True, "7", 7.5, -1, [1]])
def test_a_limit_that_is_not_a_whole_number_reads_as_0_so_the_board_refuses_it(
    given: object,
) -> None:
    assert AgentChange.model_validate({"max_seconds": given}).max_seconds == 0


@pytest.mark.parametrize("given", [True, "1.5", [1]])
def test_a_dollar_amount_that_is_not_a_number_reads_as_nan(given: object) -> None:
    value = AgentChange.model_validate({"input_price": given}).input_price
    assert isinstance(value, float)
    assert math.isnan(value)


def test_a_whole_dollar_amount_reads_as_a_float() -> None:
    assert AgentChange.model_validate({"max_daily_usd": 4}).max_daily_usd == 4.0


def test_a_change_refuses_a_field_it_does_not_know() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        AgentChange.model_validate({"key_env": "X"})
