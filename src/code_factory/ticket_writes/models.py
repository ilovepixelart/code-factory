"""What the ticket write rules and service take and answer.

Field values are text exactly as the app shows them: `labels` is `a, b`, `blocked_by` is
`CF-1, CF-3`, `archived` is `true` or empty.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from code_factory.tickets.models import NewTicket
from code_factory.undo.models import Changed

PRIORITIES = ("urgent", "high", "medium", "low")
TYPES = ("feature", "bug", "refactor", "upgrade", "hotfix", "docs")
STAGES = ("spec", "build", "review", "merged")
DEFAULT_TYPE = "feature"
CARD_FIELDS = ("labels", "priority", "assignee", "due", "blocked", "archived")
LIST_FIELDS = ("labels", "blocked_by", "caused_by")
LINK_FIELDS = ("parent", "blocked_by", "caused_by")
PLAIN_FIELDS = (
    "title", "type", "description", "e2e", "tests", "budget", "parallel", "source", "steps",
    "pages", "branch",
)  # fmt: skip
EDITABLE = frozenset((*PLAIN_FIELDS, *CARD_FIELDS, "parent", "blocked_by", "caused_by", "stage"))
CREATE_FIELDS = frozenset(
    (
        "title",
        "type",
        "branch",
        "description",
        "stage",
        "budget",
        "parent",
        "blocked_by",
        "tests",
        "e2e",
        "parallel",
        "pages",
        "source",
        "caused_by",
        *CARD_FIELDS,
    )
)
# What an intake token may send when it files a ticket.
TOKEN_CREATE_FIELDS = frozenset(
    {"repository", "title", "type", "description", "labels", "priority"}
)
LINK_KINDS = ("parent", "child", "blocked_by", "blocks")


class _Value(BaseModel):
    model_config = ConfigDict(frozen=True)


class Record(_Value):
    """One activity record a write makes: its kind and data."""

    kind: str
    data: dict[str, Any] = Field(default_factory=dict)


class CreatePlan(_Value):
    """What a create writes: the ticket, its branch and archived flag, and its records."""

    ticket: NewTicket
    branch: str
    archived: bool
    activity: list[Record]


class UpdatePlan(_Value):
    """What an update writes.

    `values` holds the changed fields as text in the order given (`branch` among them, `stage`
    and `archived` never); `stage` is the column named, if any; `archived` is the new flag when
    it flipped.
    """

    values: dict[str, str]
    stage: str
    archived: bool | None
    activity: list[Record]

    @property
    def changed(self) -> list[str]:
        """The names of the fields that differed, `archived` last."""
        return [*self.values, *(["archived"] if self.archived is not None else [])]


class LinkChange(_Value):
    """One link write: the ticket that holds it, its field and the new text."""

    holder: str
    field: str
    value: str


class BulkChoice(_Value):
    """The one action of a bulk change and the tickets (`repository/id`) it names."""

    field: str
    value: str
    tickets: list[str]


class UpdateResult(Changed):
    """The app's answer to an edit, and the names of the fields that differed (for MCP)."""

    changed: list[str]
