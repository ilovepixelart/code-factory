"""What a running run has done so far, as the ticket page shows it."""

from pydantic import BaseModel, ConfigDict


class ToolCounts(BaseModel):
    """A run's tool calls so far.

    `repeated` is how many of the last calls in a row are one call: the same tool with the same
    arguments. `last_tool` is empty with no call.
    """

    model_config = ConfigDict(frozen=True)

    calls: int = 0
    reads: int = 0
    changes: int = 0
    repeated: int = 0
    last_tool: str = ""


class ChangedFiles(BaseModel):
    """The files changed in a run's worktree since it started: how many, and the first by name."""

    model_config = ConfigDict(frozen=True)

    count: int
    names: tuple[str, ...]


class RunProgress(BaseModel):
    """What the ticket page shows of an active run; a number the log cannot give is `None`.

    `last_activity` is when the log last grew, in epoch seconds.
    """

    model_config = ConfigDict(frozen=True)

    tool_calls: int | None = None
    reads: int | None = None
    changes: int | None = None
    files: ChangedFiles | None = None
    tokens: int | None = None
    last_activity: float | None = None
