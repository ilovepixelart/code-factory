"""The answer to "what is this service"."""

from pydantic import BaseModel


class About(BaseModel):
    """Name and version of the running build."""

    name: str
    version: str
