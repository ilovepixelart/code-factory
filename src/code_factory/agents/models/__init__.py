"""Pure pydantic models and constants of the agents module.

`ConnectionDefinition`, `AgentChange` and `ConnectionChange` are re-exported for the modules that
name a connection or add an agent through the agents service (a module imports another's `models`
package, not its files).
"""

from code_factory.agents.models.agents import AgentChange
from code_factory.agents.models.connections import ConnectionChange, ConnectionDefinition
from code_factory.agents.models.prompt import PromptParts

__all__ = ["AgentChange", "ConnectionChange", "ConnectionDefinition", "PromptParts"]
