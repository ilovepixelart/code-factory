"""A capture as the screens module reads it."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

CAPTURED = "capture"
APPROVED = "capture_approved"
CHANGES = "capture_changes"
KINDS = (CAPTURED, APPROVED, CHANGES)
# The same pages as the default branch shows them, for the pull request to set beside the change;
# no verdict waits on it, so it is not one of KINDS.
BEFORE = "capture_before"


class Capture(BaseModel):
    """A ticket's capture: the tree it shows, its images and when it was taken."""

    model_config = ConfigDict(frozen=True)

    ticket: str
    tree: str
    images: tuple[str, ...]
    at: datetime
