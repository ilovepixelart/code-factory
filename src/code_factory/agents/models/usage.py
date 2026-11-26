"""What a run's log says it used."""

from pydantic import BaseModel


class LogUsage(BaseModel):
    """The cost, tokens and model a run's runtime reported; `None` for what no record says.

    A record of no known shape gives `None`, never 0.
    """

    cost: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None

    @property
    def tokens(self) -> int | None:
        """Input plus output tokens; `None` when neither was reported."""
        if self.input_tokens is None and self.output_tokens is None:
            return None
        return (self.input_tokens or 0) + (self.output_tokens or 0)


class Limit(BaseModel):
    """A run's end on its runtime's usage limit.

    `reset` is epoch seconds; `None` when the runtime stated no reset a program can read.
    """

    reset: float | None = None


class Price(BaseModel):
    """Dollars per million tokens."""

    input: float
    output: float
