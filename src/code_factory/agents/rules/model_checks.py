"""An agent's model tested with one tool call and one JSON answer.

Sent in the shape its runtime speaks to a connection on this machine; no key is sent, since only
a local connection is checked and it reads none.
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from code_factory.agents.models.agents import AgentDefinition
from code_factory.agents.models.checks import ModelCheck
from code_factory.agents.models.connections import ConnectionDefinition, Silence
from code_factory.agents.models.constants import ANTHROPIC_VERSION
from code_factory.agents.rules.connections import address, rules, runs_here
from code_factory.platform.errors import BadRequestError

SECONDS = 60
MAX_TOKENS = 1024
TOOL = "add"
TOOL_ASK = "Add 2 and 3 with the add tool."
JSON_ASK = (
    'Answer with only a JSON object whose key "sum" holds the sum of 2 and 3, and nothing else.'
)
RAN_OUT = f"ran out of its {MAX_TOKENS:,} tokens before answering"
EXCERPT = 40


class Ask(Enum):
    """What a request asks of the model."""

    TOOL = "tool"
    JSON = "json"


@dataclass(frozen=True)
class Request:
    """One request of a check: what it asks, where it goes, its header lines and its body."""

    ask: Ask
    address: str
    headers: list[str]
    body: dict[str, Any]


def _messages(runtime: str) -> bool:
    """Whether `runtime` speaks Anthropic's Messages API (claude) rather than chat completions."""
    return runtime == "claude"


def check_target(
    agent: AgentDefinition, connections: list[ConnectionDefinition]
) -> ConnectionDefinition:
    """The connection an agent's model is checked on: one on this machine that keeps the rules."""
    connection = next(
        (c for c in connections if agent.connection and c.name == agent.connection), None
    )
    if connection is None:
        msg = f"agent {agent.name} has no connection on this machine to check its model on"
        raise BadRequestError(msg)
    if not runs_here(connection):
        msg = f"connection {connection.name} is not on this machine; only a local model is checked"
        raise BadRequestError(msg)
    try:
        rules(connection)
    except BadRequestError as why:
        msg = f"connection {connection.name}: {why}"
        raise BadRequestError(msg) from None
    if not agent.model:
        msg = f"agent {agent.name} names no model to check"
        raise BadRequestError(msg)
    return connection


_SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
    "required": ["a", "b"],
}
_DESCRIPTION = "Adds two whole numbers."


def check_requests(
    runtime: str, connection: ConnectionDefinition, model: str
) -> tuple[Request, Request]:
    """The two requests of a check of `model` on `connection`: the tool call, then the JSON."""
    if _messages(runtime):
        path = "/v1/messages"
        headers = ["content-type: application/json", f"anthropic-version: {ANTHROPIC_VERSION}"]
        tool: dict[str, Any] = {
            "name": TOOL,
            "description": _DESCRIPTION,
            "input_schema": _SCHEMA,
        }
    else:
        path = "/v1/chat/completions"
        headers = ["content-type: application/json"]
        tool = {
            "type": "function",
            "function": {"name": TOOL, "description": _DESCRIPTION, "parameters": _SCHEMA},
        }
    where = address(connection).with_path(path)

    def body(asked: str) -> dict[str, Any]:
        return {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": asked}],
        }

    return (
        Request(Ask.TOOL, where, headers, {**body(TOOL_ASK), "tools": [tool]}),
        Request(Ask.JSON, where, headers, body(JSON_ASK)),
    )


@dataclass(frozen=True)
class _Reply:
    """What a model answered: its tool calls, its text, and whether it stopped at its limit."""

    calls: list[tuple[str, Any]]
    text: str
    cut: bool


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _messages_reply(body: dict[str, Any]) -> _Reply:
    raw = body.get("content")
    content = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    return _Reply(
        calls=[
            (_text(item.get("name")), item.get("input"))
            for item in content
            if item.get("type") == "tool_use"
        ],
        text="".join(_text(item.get("text")) for item in content if item.get("type") == "text"),
        cut=body.get("stop_reason") == "max_tokens",
    )


def _arguments(text: str) -> Any:  # noqa: ANN401  # JSON of any shape, or the text when it is not
    try:
        return json.loads(text)
    except ValueError:
        return text


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _chat_reply(body: dict[str, Any]) -> _Reply:
    choices = body.get("choices")
    choice = _object(choices[0] if isinstance(choices, list) and choices else None)
    message = _object(choice.get("message"))
    calls = [
        (
            _text(_object(call.get("function")).get("name")),
            _arguments(_text(_object(call.get("function")).get("arguments"))),
        )
        for call in _list(message.get("tool_calls"))
        if isinstance(call, dict)
    ]
    return _Reply(calls, _text(message.get("content")), choice.get("finish_reason") == "length")


def _shown(arguments: Any) -> str:  # noqa: ANN401
    return arguments if isinstance(arguments, str) else json.dumps(arguments, separators=(",", ":"))


def _pair(arguments: Any) -> tuple[int, int] | None:  # noqa: ANN401
    if not isinstance(arguments, dict):
        return None
    a, b = arguments.get("a"), arguments.get("b")
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in (a, b)):
        return None
    return min(a, b), max(a, b)


def _tool_verdict(reply: _Reply) -> str | None:
    if not reply.calls:
        return RAN_OUT if reply.cut else "answered without a tool call"
    name, arguments = reply.calls[0]
    if name != TOOL:
        return f"called {name} instead of {TOOL}"
    if _pair(arguments) == (2, 3):
        return None
    return f"called {TOOL} with {_shown(arguments)} instead of a 2 and b 3"


def _unfenced(text: str) -> str:
    """`text` out of the one Markdown code fence around it, if any."""
    if text.startswith("```") and text.endswith("```") and "\n" in text:
        inner = text.removeprefix("```").removesuffix("```")
        return inner.split("\n", 1)[1].strip()
    return text


def _json_verdict(reply: _Reply) -> str | None:
    said = reply.text.strip()
    try:
        value = json.loads(_unfenced(said))
    except ValueError:
        value = None
    if isinstance(value, dict):
        total = value.get("sum")
        ok = isinstance(total, int) and not isinstance(total, bool) and total == 5  # noqa: PLR2004
        return None if ok else 'answered a JSON object without "sum": 5'
    if reply.cut:
        return RAN_OUT
    return f"answered text that is not a JSON object: {said[:EXCERPT]}"


def verdict(
    runtime: str,
    kind: str,
    model: str,
    ask: Ask,
    answer: tuple[int, str] | Silence,
) -> str | None:
    """The problem an answer shows, or None when it passes.

    `answer` is the status and body, or why none came back. LM Studio answers a model it does
    not hold with the one it does, so its answer's `model` must be the agent's.
    """
    if isinstance(answer, Silence):
        if answer is Silence.NO_ANSWER:
            return f"no answer in {SECONDS} seconds"
        return Silence.REFUSED.value
    status, text = answer
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    body: dict[str, Any] = parsed if isinstance(parsed, dict) else {}
    if status != 200:  # noqa: PLR2004
        error = body.get("error")
        why = error.get("message") if isinstance(error, dict) else None
        return f"HTTP {status}: {why}" if isinstance(why, str) else f"HTTP {status}"
    by = body.get("model")
    if kind == "lm-studio" and isinstance(by, str) and by != model:
        return f"answered by {by} instead of {model}"
    reply = _messages_reply(body) if _messages(runtime) else _chat_reply(body)
    return _tool_verdict(reply) if ask is Ask.TOOL else _json_verdict(reply)


def current(check: ModelCheck | None, agent: AgentDefinition) -> ModelCheck | None:
    """The kept result when it was taken with the agent's runtime, connection and model."""
    if check is None:
        return None
    same = (check.runtime, check.connection, check.model) == (
        agent.runtime,
        agent.connection,
        agent.model,
    )
    return check if same else None


def run_refusal(check: ModelCheck | None, agent: AgentDefinition) -> str | None:
    """Why a run of `agent` may not start: its current check failed; None when it passed or none."""
    kept = current(check, agent)
    if kept is None or kept.passed:
        return None
    return (
        f"agent {agent.name}: {agent.model} failed its model check ({kept.problem}); "
        "test it again on the Agents page"
    )
