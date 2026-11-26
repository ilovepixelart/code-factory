"""The agents service: the one public API of the module.

Other modules import this package and `code_factory.agents.models`, nothing else.
"""

from pathlib import Path

from pydantic import SecretStr

from code_factory.agents.models.answers import UndoStep
from code_factory.agents.models.claude_agents import ClaudeAgentList
from code_factory.agents.service.broker import BrokerSource
from code_factory.agents.service.checks import ChecksService
from code_factory.agents.service.connections import ConnectionsService
from code_factory.agents.service.kit import CommandParts, KitService, StartKit
from code_factory.agents.service.roster import RosterService

__all__ = ["AgentService", "CommandParts", "StartKit"]


class AgentService(RosterService, ConnectionsService, ChecksService, KitService, BrokerSource):
    """Agents, connections, model checks, keys, Claude Code's agent files and the broker's reads."""

    async def undo(self, step: UndoStep) -> None:
        """Apply the inverse of a write; `ConflictError` when its target changed since."""
        if step.kind.startswith("connection."):
            await self.undo_connection(step)
        else:
            await self.undo_agent(step)

    async def read_key(self, name: str) -> SecretStr | None:
        """The key `name` from the credential store, else the environment; never logged."""
        return await self._store.read(name)

    async def key_set(self, name: str) -> bool:
        """Whether the key is set; never its value."""
        return await self._store.has(name)

    async def store_key(self, name: str) -> int:
        """Store a key by name: the store prompts on the terminal; the exit code."""
        return await self._store.store(name)

    async def forget_key(self, name: str) -> bool:
        """Remove the key from the credential store."""
        return await self._store.remove(name)

    async def claude_agents(self, project_roots: list[Path]) -> ClaudeAgentList:
        """Claude Code's own agent files, read only."""
        return await self._files.find(project_roots)
