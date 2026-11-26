"""The broker's ports over the agents and sessions services."""

from pydantic import SecretStr

from code_factory.agents.models import ConnectionDefinition
from code_factory.agents.service import AgentService
from code_factory.broker.models import BrokerConnection, CodexLogin
from code_factory.sessions.service import SessionService


def _definition(connection: BrokerConnection) -> ConnectionDefinition:
    return ConnectionDefinition(
        name=connection.name,
        kind=connection.kind,
        base_url=connection.base_url,
        key_env=connection.key_name,
        management_key_env=connection.management_key_name,
    )


class AgentConnections:
    """`ConnectionSource` over the agents service."""

    def __init__(self, agents: AgentService) -> None:
        self._agents = agents

    async def get_connection(self, name: str) -> BrokerConnection:
        """The connection as the broker reads it."""
        found = await self._agents.connection_definition(name)
        return BrokerConnection(
            name=found.name,
            kind=found.kind,
            base_url=found.base_url,
            key_name=found.key_env,
            management_key_name=found.management_key_env,
        )

    def check_rules(self, connection: BrokerConnection) -> None:
        """Raise `BadRequestError` with the rule the connection breaks."""
        self._agents.check_connection(_definition(connection))

    def model_host(self, connection: BrokerConnection) -> str:
        """The connection's checked `host:port`."""
        return self._agents.model_host(_definition(connection))

    async def read_key(self, name: str) -> SecretStr | None:
        """The key kept under `name`."""
        return await self._agents.read_key(name)

    async def read_codex_login(self) -> CodexLogin:
        """The owner's login, read now."""
        login = await self._agents.read_codex_login()
        return CodexLogin(access_token=login.access_token, account_id=login.account_id)


class SessionUsage:
    """`UsageSink` over the sessions service."""

    def __init__(self, sessions: SessionService) -> None:
        self._sessions = sessions

    async def record_run_requests(self, run_id: str, export: object) -> None:
        """Keep the requests a run's telemetry export reported."""
        await self._sessions.record_run_requests(run_id, export)
