"""What the hooks service takes and answers: plain values, no behaviour."""

from pydantic import BaseModel, ConfigDict, Field


class OpenerUnavailableError(Exception):
    """No program can open a browser here."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class HookCommands(_Frozen):
    """The command strings the agent and install code write into settings, one per hook.

    `rewrite`, `tell`, `permission` and `recall` start the stdlib hook launcher by path;
    `recall_cli` is the full `code-factory recall` for the owner's own sessions.
    """

    rewrite: str
    tell: str
    permission: str
    recall: str
    recall_cli: str


class TellConfirm(_Frozen):
    """How far a session has been given the news: what `confirm_tell` marks as delivered."""

    model_config = ConfigDict(frozen=True, strict=True)

    through_post: int = Field(ge=0)
    through_answer: int = Field(ge=0)
    message_ids: list[int]


class TellAnswer(_Frozen):
    """The hook text for a session (`None`: print nothing) and the marks to confirm it with."""

    output: str | None = None
    confirm: TellConfirm | None = None


class RecallParts(_Frozen):
    """What a recall holds before its cap.

    `memory` and `left` are `(id, line)` pairs in load order: the entries kept by the memory
    budget and the ones it cut. `overflow` is the line saying the rules pass the budget; `index`
    the archived entries' lines.
    """

    memory: list[tuple[str, str]]
    left: list[tuple[str, str]]
    ticket: list[str]
    notices: list[str]
    overflow: str | None
    index: list[str]


class RecalledText(_Frozen):
    """The recall text within its cap, and how many memory entries and ticket lines it holds."""

    text: str
    memory_kept: int
    ticket_kept: int


class OpenedBoard(_Frozen):
    """What `open` did: the line it prints."""

    line: str


class ReportFields(_Frozen):
    """A production error report after reading: every field is trimmed, masked and cut."""

    fingerprint: str
    title: str
    message: str
    release: str


class ReleaseFact(_Frozen):
    """A published release as an error report reads it: when it shipped and which tickets."""

    version: str
    at: float
    tickets: list[str]


class Tie(_Frozen):
    """The release a new report follows: the tickets it shipped and the description paragraph."""

    caused_by: list[str]
    paragraph: str


class ErrorReported(_Frozen):
    """The ticket an error report landed on, how many times it was reported, and whether new."""

    ticket_id: str
    count: int
    created: bool
