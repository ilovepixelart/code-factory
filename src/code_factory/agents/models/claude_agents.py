"""Claude Code's own agent files, listed read only."""

from pydantic import BaseModel


class ClaudeAgent(BaseModel):
    """One Claude Code agent as its file defines it, and where.

    `model` is empty when it inherits the session's model, `tools` empty for every tool, `place`
    `global` or the folder name of the repository that defines it.
    """

    name: str
    description: str
    model: str = ""
    tools: list[str] = []
    place: str
    path: str


class Unread(BaseModel):
    """An agent file that does not read, and why."""

    path: str
    why: str


class ClaudeAgentList(BaseModel):
    """The agent files found, and the files that are not agents."""

    agents: list[ClaudeAgent]
    unread: list[Unread]
