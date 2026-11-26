"""What the repositories service answers."""

from pydantic import BaseModel


class RepositoryRecord(BaseModel):
    """A tracked repository: `name` is its folder name, `path` its main checkout."""

    name: str
    path: str
