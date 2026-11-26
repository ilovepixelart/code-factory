"""A model is judged by one tool call and one JSON answer, in the shape its runtime speaks:
Messages for claude, chat completions for codex. Cases are those of the previous
implementation's `model_checks` tests, with its sentences."""

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from code_factory.agents.models.agents import AgentDefinition
from code_factory.agents.models.checks import ModelCheck
from code_factory.agents.models.connections import ConnectionDefinition, Silence
from code_factory.agents.rules.model_checks import (
    Ask,
    check_requests,
    check_target,
    current,
    run_refusal,
    verdict,
)
from code_factory.platform.errors import BadRequestError


def message(content: list[dict[str, Any]], stop: str, model: str = "m-1") -> str:
    return json.dumps({"type": "message", "model": model, "content": content, "stop_reason": stop})


def completion(content: str, calls: list[tuple[str, str]], finish: str, model: str = "m-1") -> str:
    tool_calls = [
        {"type": "function", "id": "c-1", "function": {"name": n, "arguments": a}} for n, a in calls
    ]
    return json.dumps(
        {
            "model": model,
            "choices": [
                {
                    "message": {"role": "assistant", "content": content, "tool_calls": tool_calls},
                    "finish_reason": finish,
                }
            ],
        }
    )


def use_tool(name: str, arguments: dict[str, Any], model: str = "m-1") -> str:
    return message(
        [{"type": "tool_use", "id": "t", "name": name, "input": arguments}], "tool_use", model
    )


def text(said: str, stop: str = "end_turn") -> str:
    return message([{"type": "text", "text": said}], stop)


def judged(
    runtime: str, ask: Ask, answer: tuple[int, str] | Silence, kind: str = "lm-studio"
) -> str:
    return verdict(runtime, kind, "m-1", ask, answer) or "passes"


def both(tool_messages: str, tool_chat: str, ask: Ask = Ask.TOOL) -> tuple[str, str]:
    return judged("claude", ask, (200, tool_messages)), judged("codex", ask, (200, tool_chat))


def same(one: str) -> tuple[str, str]:
    return one, one


def test_a_tool_call_to_add_with_2_and_3_passes_in_either_order_in_both_shapes() -> None:
    assert both(
        use_tool("add", {"a": 3, "b": 2}),
        completion("", [("add", '{"a": 3, "b": 2}')], "tool_calls"),
    ) == same("passes")
    assert both(
        use_tool("add", {"a": 2, "b": 3}), completion("", [("add", '{"a":2,"b":3}')], "tool_calls")
    ) == same("passes")


def test_a_reply_without_a_tool_call_or_with_another_tool_is_worded_as_it_was() -> None:
    assert both(
        text("I would add them: 5."), completion("I would add them: 5.", [], "stop")
    ) == same("answered without a tool call")
    assert both(
        use_tool("sum", {"a": 2, "b": 3}), completion("", [("sum", '{"a":2,"b":3}')], "tool_calls")
    ) == same("called sum instead of add")


def test_wrong_arguments_are_shown_as_given() -> None:
    assert both(
        use_tool("add", {"a": "2", "b": 3}),
        completion("", [("add", '{"a":"2","b":3}')], "tool_calls"),
    ) == same('called add with {"a":"2","b":3} instead of a 2 and b 3')
    assert judged("claude", Ask.TOOL, (200, use_tool("add", {"a": 2, "b": 4}))) == (
        'called add with {"a":2,"b":4} instead of a 2 and b 3'
    )
    assert judged(
        "codex", Ask.TOOL, (200, completion("", [("add", "not json")], "tool_calls"))
    ) == ("called add with not json instead of a 2 and b 3")


def test_a_reply_cut_at_the_token_limit_says_it_ran_out() -> None:
    assert both(
        text("Let me think about", "max_tokens"), completion("Let me think about", [], "length")
    ) == same("ran out of its 1,024 tokens before answering")


def test_an_http_error_shows_its_message_when_the_server_gives_one() -> None:
    claude = (
        '{"type":"error","error":{"type":"invalid_request_error","message":"No models loaded"}}'
    )
    chat = '{"error":{"message":"No models loaded","type":"invalid_request_error","code":null}}'
    assert judged("claude", Ask.TOOL, (400, claude)) == "HTTP 400: No models loaded"
    assert judged("codex", Ask.TOOL, (400, chat)) == "HTTP 400: No models loaded"
    assert judged("claude", Ask.TOOL, (500, "")) == "HTTP 500"


def test_a_server_that_does_not_answer_or_refuses_is_worded() -> None:
    assert judged("claude", Ask.TOOL, Silence.NO_ANSWER) == "no answer in 60 seconds"
    assert judged("claude", Ask.TOOL, Silence.REFUSED) == "connection refused"


def test_lm_studio_answering_with_another_model_fails_and_others_do_not() -> None:
    other = use_tool("add", {"a": 2, "b": 3}, model="other")
    assert judged("claude", Ask.TOOL, (200, other)) == "answered by other instead of m-1"
    assert judged("claude", Ask.TOOL, (200, other), kind="ollama") == "passes"


@pytest.mark.parametrize(
    "said",
    ['{"sum": 5}', '```json\n{"sum": 5}\n```', '```\n{"sum":5}\n```', '  {"sum": 5}\n'],
)
def test_a_json_object_with_sum_5_passes_with_one_code_fence_tolerated(said: str) -> None:
    assert both(text(said), completion(said, [], "stop"), Ask.JSON) == same("passes")


@pytest.mark.parametrize(
    ("said", "problem"),
    [
        ("The sum is 5.", "answered text that is not a JSON object: The sum is 5."),
        ('{"total": 5}', 'answered a JSON object without "sum": 5'),
        ('{"sum": 6}', 'answered a JSON object without "sum": 5'),
        ("[5]", "answered text that is not a JSON object: [5]"),
        (
            'Here is the object you asked for, with the sum: {"sum": 5}',
            "answered text that is not a JSON object: Here is the object you asked for, with t",
        ),
    ],
)
def test_any_other_json_answer_is_worded_with_the_first_40_characters(
    said: str, problem: str
) -> None:
    assert both(text(said), completion(said, [], "stop"), Ask.JSON) == same(problem)


def connection(
    kind: str = "lm-studio", base_url: str = "http://localhost:1234"
) -> ConnectionDefinition:
    return ConnectionDefinition(name="local", kind=kind, base_url=base_url)


def test_a_claude_check_asks_the_messages_api_with_the_version_header_and_no_key() -> None:
    tool, answer = check_requests("claude", connection(), "m-1")
    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"],
    }
    assert tool.ask is Ask.TOOL
    assert tool.address == "http://localhost:1234/v1/messages"
    assert tool.headers == ["content-type: application/json", "anthropic-version: 2023-06-01"]
    assert tool.body == {
        "model": "m-1",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "Add 2 and 3 with the add tool."}],
        "tools": [
            {"name": "add", "description": "Adds two whole numbers.", "input_schema": schema}
        ],
    }
    assert answer.ask is Ask.JSON
    assert answer.body == {
        "model": "m-1",
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": (
                    'Answer with only a JSON object whose key "sum" holds the sum of 2 and 3, '
                    "and nothing else."
                ),
            }
        ],
    }


def test_a_codex_check_asks_chat_completions_with_a_function_tool() -> None:
    tool, _ = check_requests("codex", connection("ollama", "http://localhost:11434"), "m-1")
    assert tool.address == "http://localhost:11434/v1/chat/completions"
    assert tool.headers == ["content-type: application/json"]
    assert tool.body["tools"][0]["type"] == "function"
    assert tool.body["tools"][0]["function"]["name"] == "add"


def agent(**fields: object) -> AgentDefinition:
    return AgentDefinition.model_validate(
        {"name": "q", "runtime": "claude", "connection": "local", "model": "m-1", **fields}
    )


def test_the_target_is_the_agents_local_connection_when_it_has_a_model() -> None:
    assert check_target(agent(), [connection()]).name == "local"


@pytest.mark.parametrize(
    ("changes", "kept", "why"),
    [
        (
            {"connection": ""},
            [connection()],
            "agent q has no connection on this machine to check its model on",
        ),
        ({}, [], "agent q has no connection on this machine to check its model on"),
        (
            {},
            [
                ConnectionDefinition(
                    name="local",
                    kind="anthropic",
                    base_url="https://api.anthropic.com",
                    key_env="ANTHROPIC_API_KEY",
                )
            ],
            "connection local is not on this machine; only a local model is checked",
        ),
        ({"model": ""}, [connection()], "agent q names no model to check"),
    ],
)
def test_a_check_without_a_local_connection_or_a_model_is_refused(
    changes: dict[str, str], kept: list[ConnectionDefinition], why: str
) -> None:
    given = agent(**changes)
    with pytest.raises(BadRequestError) as caught:
        check_target(given, kept)
    assert str(caught.value) == why


def test_a_connection_that_breaks_the_rules_is_refused_with_its_name() -> None:
    given = agent()
    given_2 = [connection(base_url="http://10.0.0.5:1234")]
    with pytest.raises(BadRequestError) as caught:
        check_target(given, given_2)
    assert str(caught.value) == (
        "connection local: lm-studio connections run on this machine: "
        "the address's host is localhost or 127.0.0.1"
    )


NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def kept(**fields: object) -> ModelCheck:
    return ModelCheck.model_validate(
        {
            "runtime": "claude",
            "connection": "local",
            "model": "m-1",
            "passed": False,
            "problem": "answered without a tool call",
            "at": NOW,
            **fields,
        }
    )


def test_a_kept_check_applies_only_to_what_it_was_taken_with() -> None:
    assert current(kept(), agent()) == kept()
    assert current(kept(), agent(runtime="codex")) is None
    assert current(kept(), agent(connection="cloud")) is None
    assert current(kept(), agent(model="m-2")) is None
    assert current(None, agent()) is None


def test_a_failed_check_refuses_a_run_in_the_owners_words_and_a_pass_does_not() -> None:
    assert run_refusal(kept(), agent()) == (
        "agent q: m-1 failed its model check (answered without a tool call); "
        "test it again on the Agents page"
    )
    assert run_refusal(kept(passed=True, problem=""), agent()) is None
    assert run_refusal(None, agent()) is None
    assert run_refusal(kept(model="old"), agent()) is None


def test_a_check_wire_is_in_whole_epoch_seconds() -> None:
    assert kept().wire() == {
        "runtime": "claude",
        "connection": "local",
        "model": "m-1",
        "passed": False,
        "problem": "answered without a tool call",
        "at": 1795435200,
    }


@pytest.mark.parametrize(
    "body",
    [
        {"content": 5},
        {"content": [5, "x", None]},
        {"content": {"type": "text"}},
        {"choices": 5},
        {"choices": [5]},
        {"choices": [{"message": {"tool_calls": 5}}]},
        {"choices": [{"message": {"tool_calls": [5, {"function": 7}]}}]},
        {"choices": [{"message": 3}]},
        [],
    ],
)
def test_a_reply_with_malformed_collections_fails_the_check_and_does_not_raise(
    body: object,
) -> None:
    for runtime in ("claude", "codex"):
        problem = verdict(runtime, "ollama", "m", Ask.TOOL, (200, json.dumps(body)))
        assert problem in ("answered without a tool call", "called  instead of add")
