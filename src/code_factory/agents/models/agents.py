"""An agent as the app reads it, and what a change to one may say."""

import math
from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


class _Kept(Enum):
    KEPT = "kept"


KEPT = _Kept.KEPT


def _limit(value: object) -> int | _Kept | None:
    """A whole number, `None` to clear, anything else 0 so the refusal is the board's sentence."""
    if value is None or value is KEPT:
        return value
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _dollars(value: object) -> float | _Kept | None:
    """A number, `None` to clear, anything else NaN so the refusal is the board's sentence."""
    if value is None or value is KEPT:
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return math.nan


Limit = Annotated[int | _Kept | None, BeforeValidator(_limit)]
Dollars = Annotated[float | _Kept | None, BeforeValidator(_dollars)]


class AgentChange(BaseModel):
    """What an add or an edit says: a field left out keeps its value; a limit set to null clears it.

    `paused` pauses (true) or resumes (false); `context` blank clears the owner's context.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    runtime: str | None = None
    connection: str | None = None
    model: str | None = None
    roles: list[str] | None = None
    types: list[str] | None = None
    labels: list[str] | None = None
    max_tokens: Limit = KEPT
    max_seconds: Limit = KEPT
    input_price: Dollars = KEPT
    output_price: Dollars = KEPT
    max_daily_usd: Dollars = KEPT
    paused: bool | None = None
    context: str | None = None


class ContextVersion(BaseModel):
    """A context an agent had before a change replaced it; `at` is when it became current."""

    at: datetime
    context: str


def epoch(moment: datetime) -> int:
    """Whole seconds since the epoch."""
    return int(moment.timestamp())


class AgentDefinition(BaseModel):
    """One named agent. `connection` is the connection's name, empty for none."""

    name: str
    runtime: str
    connection: str = ""
    model: str = ""
    roles: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    max_tokens: int | None = None
    max_seconds: int | None = None
    input_price: float | None = None
    output_price: float | None = None
    max_daily_usd: float | None = None
    paused_at: datetime | None = None
    context: str | None = None
    context_at: datetime | None = None
    context_history: list[ContextVersion] = Field(default_factory=list)

    def wire(self) -> dict[str, Any]:
        """The answer the Vue app reads: its keys in order, empty optional ones left out."""
        wire: dict[str, Any] = {
            "name": self.name,
            "runtime": self.runtime,
            "connection": self.connection,
            "model": self.model,
            "roles": list(self.roles),
        }
        if self.types:
            wire["types"] = list(self.types)
        if self.labels:
            wire["labels"] = list(self.labels)
        wire["max_tokens"] = self.max_tokens
        wire["max_seconds"] = self.max_seconds
        for key in ("input_price", "output_price", "max_daily_usd"):
            if (value := getattr(self, key)) is not None:
                wire[key] = value
        if self.paused_at is not None:
            wire["paused_at"] = epoch(self.paused_at)
        if self.context is not None:
            wire["context"] = self.context
        if self.context_at is not None:
            wire["context_at"] = epoch(self.context_at)
        if self.context_history:
            wire["context_history"] = [
                {"at": epoch(version.at), "context": version.context}
                for version in self.context_history
            ]
        return wire
