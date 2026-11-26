"""What a connection's model list says: parsing the three list shapes, the context a server holds
a model with, and the words an agent's card and a refused start use (the previous
implementation's `probes` rules and tests)."""

import json

import pytest
from pydantic import SecretStr

from code_factory.agents.models.connections import ConnectionDefinition, Model, Status
from code_factory.agents.rules.probes import (
    context_refusal,
    key_headers,
    loaded_address,
    local_state,
    models,
    reach,
    with_loaded,
)


def studio(models: list[tuple[str, int | None]]) -> str:
    data = [
        {
            "id": name,
            "object": "model",
            "type": "llm",
            "state": "not-loaded" if loaded is None else "loaded",
            "max_context_length": 131_072,
            **({"loaded_context_length": loaded} if loaded is not None else {}),
        }
        for name, loaded in models
    ]
    return json.dumps({"data": data, "object": "list"})


def test_lm_studios_list_gives_each_models_context_and_loaded_context() -> None:
    assert models(studio([("qwen", 64_000), ("gemma", None)])) == [
        Model(id="qwen", context=131_072, loaded=64_000),
        Model(id="gemma", context=131_072, loaded=None),
    ]


def test_a_v1_list_gives_ids_and_ollamas_tags_give_names() -> None:
    assert models('{"data":[{"id":"a"},{"id":"b","context_length":8192}]}') == [
        Model(id="a"),
        Model(id="b", context=8192),
    ]
    assert models('{"models":[{"name":"llama3:8b"}]}') == [Model(id="llama3:8b")]


def test_the_training_context_of_a_llama_cpp_model_is_its_context() -> None:
    body = '{"data":[{"id":"x","meta":{"n_ctx_train":4096}}]}'
    assert models(body) == [Model(id="x", context=4096)]


def test_an_embedding_model_is_left_out_and_unreadable_bodies_list_nothing() -> None:
    body = '{"data":[{"id":"e","type":"embeddings"},{"id":"m","type":"llm"}]}'
    assert [m.id for m in models(body)] == ["m"]
    assert models("not json") == []
    assert models('{"data": 5}') == []
    assert models('{"other": []}') == []


def test_ollama_and_llama_cpp_say_the_loaded_context_where_their_list_does_not() -> None:
    listed = [Model(id="qwen"), Model(id="idle")]
    ps = '{"models":[{"name":"qwen","model":"qwen","context_length":32768}]}'
    assert with_loaded("ollama", listed, ps) == [Model(id="qwen", loaded=32768), Model(id="idle")]
    props = '{"default_generation_settings":{"n_ctx":65536}}'
    assert [m.loaded for m in with_loaded("llama-cpp", listed, props)] == [65536, 65536]
    assert with_loaded("lm-studio", listed, ps) == listed
    assert with_loaded("ollama", listed, "garbage") == listed


def test_a_local_kind_says_where_its_loaded_context_is_and_others_nowhere() -> None:
    def at(kind: str) -> str | None:
        return loaded_address(
            ConnectionDefinition(name="c", kind=kind, base_url="http://localhost:11434")
        )

    assert at("ollama") == "http://localhost:11434/api/ps"
    assert at("llama-cpp") == "http://localhost:11434/props"
    assert at("lm-studio") is None


def status(*, answers: bool = True, loaded: int | None = None, problem: str = "") -> Status:
    return Status(
        name="local",
        answers=answers,
        models=[Model(id="qwen", context=131_072, loaded=loaded)],
        problem=problem,
    )


@pytest.mark.parametrize(
    ("model", "checked", "words"),
    [
        ("qwen", status(answers=False), "does not answer"),
        ("m", None, "does not answer"),
        ("gemma", status(), "model not listed"),
        ("", status(), "answers"),
        ("qwen", status(loaded=63_999), "context 63,999 of 64,000"),
        ("qwen", status(loaded=64_000), "answers"),
        ("qwen", status(), "answers"),
        ("qwen", status(loaded=512), "context 512 of 64,000"),
    ],
)
def test_a_models_reach_is_worded_from_its_connections_check(
    model: str, checked: Status | None, words: str
) -> None:
    assert reach(model, checked) == words


def test_a_server_that_lacks_the_model_refuses_the_start_whatever_its_kind() -> None:
    listing = Status(
        name="local", answers=True, models=[Model(id="qwen", context=131_072, loaded=64_000)]
    )
    refusal = (
        "connection local: gemma is not among the models the server lists; set the agent's "
        "model to one the Agents page lists for the connection"
    )
    for kind in ("lm-studio", "ollama", "llama-cpp"):
        assert context_refusal(kind, listing, "gemma") == refusal
        assert context_refusal(kind, listing, "qwen") is None


def test_a_model_loaded_under_the_floor_is_refused_and_the_floor_itself_is_taken() -> None:
    assert context_refusal("ollama", status(loaded=64_000), "qwen") is None
    assert context_refusal("ollama", status(loaded=63_999), "qwen") == (
        "connection local: qwen is loaded with context 63,999 of 64,000; "
        "load it with a larger context"
    )
    assert context_refusal("lm-studio", status(loaded=8192), "qwen") == (
        "connection local: qwen is loaded with context 8,192 of 64,000; load it with a larger "
        "context: lms unload qwen && lms load qwen --context-length 64000"
    )


def test_lm_studio_with_the_model_not_loaded_says_how_to_load_it() -> None:
    assert context_refusal("lm-studio", status(), "qwen") == (
        "connection local: qwen is not loaded, and the server would load it with its own "
        "default context; load it with at least 64,000: lms load qwen --context-length 64000"
    )
    assert context_refusal("ollama", status(), "qwen") is None


def test_a_connection_that_does_not_answer_refuses_with_why() -> None:
    assert context_refusal("ollama", status(answers=False, problem="connection refused"), "q") == (
        "connection local: connection refused"
    )
    assert context_refusal("ollama", status(answers=False, problem="HTTP 500"), "q") == (
        "connection local: no answer"
    )


def test_a_key_goes_in_the_header_its_kind_expects() -> None:
    def connection(kind: str) -> ConnectionDefinition:
        return ConnectionDefinition(name="c", kind=kind, base_url="", key_env="K_API_KEY")

    key = SecretStr("sk-1")
    assert key_headers(connection("openrouter"), key) == {"Authorization": "Bearer sk-1"}
    assert key_headers(connection("anthropic"), key) == {
        "x-api-key": "sk-1",
        "anthropic-version": "2023-06-01",
    }
    assert key_headers(connection("openrouter"), None) == {}


@pytest.mark.parametrize(
    ("kind", "status_code", "state"),
    [
        ("lm-studio", 200, "answers"),
        ("llama-cpp", 503, "loading a model"),
        ("ollama", 503, None),
        ("ollama", 404, None),
    ],
)
def test_a_local_servers_state_comes_from_the_status_it_answered(
    kind: str, status_code: int, state: str | None
) -> None:
    assert local_state(kind, status_code) == state
