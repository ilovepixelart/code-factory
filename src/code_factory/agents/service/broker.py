"""What the key broker reads of the agents module: a connection, its checked address, the login."""

from code_factory.agents.models.connections import ConnectionDefinition
from code_factory.agents.repository import ConnectionRepository
from code_factory.agents.rules.connections import address, rules
from code_factory.agents.rules.login import CodexLogin, codex_login, login_problem
from code_factory.agents.service.base import Shared
from code_factory.platform.errors import NotFoundError, UnavailableError

_DEFAULT_PORT = {"http": "80", "https": "443"}


class BrokerSource(Shared):
    """The reads the key broker makes on every request; none of them caches."""

    async def connection_definition(self, name: str) -> ConnectionDefinition:
        """The connection `name`; `NotFoundError` when it is gone."""
        async with self._uow() as session:
            known = await ConnectionRepository(session).all()
        found = next((c for c in known if c.name == name), None)
        if found is None:
            msg = "no such connection"
            raise NotFoundError(msg)
        return found

    def check_connection(self, connection: ConnectionDefinition) -> None:
        """Raise `BadRequestError` with the rule when the connection breaks its kind's rules."""
        rules(connection)

    def model_host(self, connection: ConnectionDefinition) -> str:
        """The `host:port` of the connection's checked address, the default port spelled out."""
        parsed = address(connection)
        return f"{parsed.host}:{parsed.port or _DEFAULT_PORT[parsed.scheme]}"

    async def read_codex_login(self) -> CodexLogin:
        """The owner's ChatGPT login read from its file now; `UnavailableError` when unusable."""
        path, text = await self._login.read()
        if (problem := login_problem(str(path), text)) is not None:
            raise UnavailableError(problem)
        assert text is not None  # noqa: S101  # `login_problem` refused a missing file
        return codex_login(text)
