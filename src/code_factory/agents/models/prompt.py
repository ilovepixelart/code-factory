"""What a run's prompt is made of."""

from pydantic import BaseModel, ConfigDict, Field


class PromptParts(BaseModel):
    """The parts of one run's prompt; every list is oldest first.

    `owner` is the agent's context block (`fence.context_block`), empty without one; `harness` is
    a local build run's section (`harness`), empty for every other run. `nonce` is drawn for the
    run and names the end line of every fence the prompt holds, so no text can forge one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    title: str
    kind: str
    branch: str
    stage: str
    task: str
    nonce: str = Field(pattern=r"^[A-Za-z0-9]{8,64}$")
    source: str = ""
    present: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    comments: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    harness: str = ""
    owner: str = ""


class InlineFile(BaseModel):
    """One document or file named by a spec, as the tickets service read it for a local prompt.

    `data` is `None` when it did not read as a plain file; at most one byte past the file bound is
    read, so a longer file is cut by the harness, not by the reader.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    data: bytes | None = None
