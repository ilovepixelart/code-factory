"""What a connection's model list gives, and how an agent's card and a start refusal word it."""

import json
from typing import Any

from pydantic import SecretStr

from code_factory.agents.models.connections import ConnectionDefinition, Model, Silence, Status
from code_factory.agents.models.constants import ANTHROPIC_VERSION, CONTEXT_FLOOR
from code_factory.agents.rules.connections import address

STUDIO_MODELS = "/api/v0/models"
# The local servers the board looks for: each kind and the path that answers on its default address.
LOCAL_PROBES = (("lm-studio", STUDIO_MODELS), ("ollama", "/api/tags"), ("llama-cpp", "/health"))


def loaded_address(connection: ConnectionDefinition) -> str | None:
    """Where a server whose list leaves it out says the context it holds its models with."""
    path = {"ollama": "/api/ps", "llama-cpp": "/props"}.get(connection.kind)
    return None if path is None else address(connection).with_path(path)


def _object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _whole(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _loaded(kind: str, model: str, running: Any, served: int | None) -> int | None:  # noqa: ANN401
    if kind == "llama-cpp":
        return served
    if kind != "ollama" or not isinstance(running, list):
        return None
    for item in running:
        if isinstance(item, dict) and model in (item.get("name"), item.get("model")):
            return _whole(item.get("context_length"))
    return None


def with_loaded(kind: str, listed: list[Model], body: str) -> list[Model]:
    """`listed` with the loaded contexts `body`, the answer of `loaded_address`, gives.

    Ollama's `models[].context_length` by name; llama.cpp's `n_ctx` for every model, since it
    serves one.
    """
    value = _object(body)
    served_settings = value.get("default_generation_settings")
    served = _whole(served_settings.get("n_ctx")) if isinstance(served_settings, dict) else None
    running = value.get("models")
    return [
        model.model_copy(
            update={"loaded": _loaded(kind, model.id, running, served) or model.loaded}
        )
        for model in listed
    ]


def _context_of(item: dict[str, Any]) -> int | None:
    meta = item.get("meta")
    for found in (
        item.get("context_length"),
        item.get("max_context_length"),
        meta.get("n_ctx_train") if isinstance(meta, dict) else None,
    ):
        if (context := _whole(found)) is not None:
            return context
    return None


def models(body: str) -> list[Model]:
    """The models in a server's answer, `data[].id` or `models[].name`, embeddings left out."""
    value = _object(body)
    if isinstance(value.get("data"), list):
        items, key = value["data"], "id"
    elif isinstance(value.get("models"), list):
        items, key = value["models"], "name"
    else:
        return []
    return [
        Model(
            id=item[key],
            context=_context_of(item),
            loaded=_whole(item.get("loaded_context_length")),
        )
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get(key), str)
        and item.get("type") != "embeddings"
    ]


def reach(model: str, checked: Status | None) -> str:
    """What the last check says of `model` on its connection, as the agent's card words it."""
    if checked is None or not checked.answers:
        return "does not answer"
    listed = next((m for m in checked.models if m.id == model), None)
    if model and listed is None:
        return "model not listed"
    if listed is not None and listed.loaded is not None and listed.loaded < CONTEXT_FLOOR:
        return f"context {listed.loaded:,} of {CONTEXT_FLOOR:,}"
    return "answers"


def context_refusal(kind: str, checked: Status, model: str) -> str | None:
    """Why a run of `model` on the connection would not fit; None when it fits.

    The server gave no answer, lists no such model, holds it with less than the floor, or (LM
    Studio) has not loaded it and would load it with a default the list does not say.
    """
    name = checked.name
    if not checked.answers:
        why = Silence.REFUSED if checked.problem == Silence.REFUSED else Silence.NO_ANSWER
        return f"connection {name}: {why.value}"
    listed = next((m for m in checked.models if m.id == model), None)
    if listed is None:
        return (
            f"connection {name}: {model} is not among the models the server lists; set the "
            "agent's model to one the Agents page lists for the connection"
        )
    studio = kind == "lm-studio"
    load = f"lms load {model} --context-length {CONTEXT_FLOOR}"
    if listed.loaded is None and studio:
        return (
            f"connection {name}: {model} is not loaded, and the server would load it with its "
            f"own default context; load it with at least {CONTEXT_FLOOR:,}: {load}"
        )
    if listed.loaded is not None and listed.loaded < CONTEXT_FLOOR:
        fix = f": lms unload {model} && {load}" if studio else ""
        return (
            f"connection {name}: {model} is loaded with context {listed.loaded:,} of "
            f"{CONTEXT_FLOOR:,}; load it with a larger context{fix}"
        )
    return None


def key_headers(connection: ConnectionDefinition, key: SecretStr | None) -> dict[str, str]:
    """The headers that carry a connection's key, as its kind expects; none without a key."""
    if key is None:
        return {}
    if connection.kind == "anthropic":
        return {"x-api-key": key.get_secret_value(), "anthropic-version": ANTHROPIC_VERSION}
    return {"Authorization": f"Bearer {key.get_secret_value()}"}


def local_state(kind: str, status: int) -> str | None:
    """A local server's state from the status it answered; None when it is not running."""
    if status == 200:  # noqa: PLR2004
        return "answers"
    if status == 503 and kind == "llama-cpp":  # noqa: PLR2004
        return "loading a model"
    return None
