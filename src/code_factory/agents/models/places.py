"""Where a contained run's git work lands."""

from pydantic import BaseModel, ConfigDict


class GitPlaces(BaseModel):
    """A run's worktree, its own git folder, the repository's and the branch it commits on.

    The branch is empty for none; every path is resolved.
    """

    model_config = ConfigDict(frozen=True)

    worktree: str
    admin: str
    common: str
    branch: str = ""
