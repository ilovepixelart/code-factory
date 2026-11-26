"""Answers of the liveness and readiness probes and the error body."""

from typing import Literal

from pydantic import BaseModel


class Health(BaseModel):
    """The process is up."""

    status: Literal["ok"]


class Ready(BaseModel):
    """The process can reach its database."""

    status: Literal["ready"]
