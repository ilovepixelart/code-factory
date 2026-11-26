"""A model connection as the app reads it, what a change says, and what asking one returns."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True)
class Kind:
    """A kind of connection: its label, default address, key policy, host and local token.

    `host` is the one https host a keyed kind's requests and key go to; empty means this machine
    only. `token` is what a run sends to a local server that checks no key.
    """

    kind: str
    label: str
    base_url: str
    key: Literal["required", "none", "login"]
    host: str = ""
    token: str = ""

    def wire(self) -> dict[str, str]:
        """The kind as the Vue app reads it: host and token are not part of it."""
        return {"kind": self.kind, "label": self.label, "base_url": self.base_url, "key": self.key}


class ConnectionDefinition(BaseModel):
    """One named connection. `key_env` is the name the key is kept under, never the key."""

    name: str
    kind: str
    base_url: str
    key_env: str = ""
    management_key_env: str | None = None

    def wire(self) -> dict[str, Any]:
        """The answer the Vue app reads."""
        wire: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "base_url": self.base_url,
            "key_env": self.key_env,
        }
        if self.management_key_env is not None:
            wire["management_key_env"] = self.management_key_env
        return wire


class ConnectionChange(BaseModel):
    """What an add or an edit says: each field it names. A blank management key clears it."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    kind: str | None = None
    base_url: str | None = None
    key_env: str | None = None
    management_key_env: str | None = None


class Model(BaseModel):
    """A model a server offers: its context length, and the context it is loaded with."""

    id: str
    context: int | None = None
    loaded: int | None = None


class Status(BaseModel):
    """Whether a connection answers, its models, or why it does not."""

    name: str
    answers: bool
    models: list[Model] = []
    problem: str = ""


class Found(BaseModel):
    """A local server found on this machine."""

    kind: str
    base_url: str
    state: str
    models: list[Model] = []


class Silence(StrEnum):
    """Why a request got no status back; the value is the problem a status words."""

    NO_ANSWER = "no answer"
    REFUSED = "connection refused"
