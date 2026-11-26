"""The base of every value this module hands out."""

from pydantic import BaseModel, ConfigDict


class Dto(BaseModel):
    """A value that never changes after it is built and refuses fields it does not name."""

    model_config = ConfigDict(frozen=True, extra="forbid")
