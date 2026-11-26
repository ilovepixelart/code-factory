"""An agent's model check: the last result, with what it was taken with."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from code_factory.agents.models.agents import epoch


class ModelCheck(BaseModel):
    """An agent's last result, with the runtime, connection name and model it was taken with."""

    runtime: str
    connection: str
    model: str
    passed: bool
    problem: str = ""
    at: datetime

    def wire(self) -> dict[str, Any]:
        """The answer the Vue app reads: `at` in whole epoch seconds."""
        return {
            "runtime": self.runtime,
            "connection": self.connection,
            "model": self.model,
            "passed": self.passed,
            "problem": self.problem,
            "at": epoch(self.at),
        }
