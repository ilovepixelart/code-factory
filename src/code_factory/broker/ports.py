"""What the broker reads and drives in other modules, as protocols over its own shapes.

`service/neighbours.py` implements each over the owning module's service; a test supplies fakes.
"""

from collections.abc import Sequence
from typing import Protocol

from pydantic import SecretStr

from code_factory.broker.models import BrokerConnection, CodexLogin


class ConnectionSource(Protocol):
    """The agents module's connections and keys."""

    async def get_connection(self, name: str) -> BrokerConnection:
        """The connection; `NotFoundError` when it is gone."""
        ...

    def check_rules(self, connection: BrokerConnection) -> None:
        """Raise `BadRequestError` with the rule the connection breaks."""
        ...

    def model_host(self, connection: BrokerConnection) -> str:
        """The `host:port` of the connection's checked address."""
        ...

    async def read_key(self, name: str) -> SecretStr | None:
        """The key kept under `name`, read now and never cached."""
        ...

    async def read_codex_login(self) -> CodexLogin:
        """The owner's login read now; `UnavailableError` with the sentence when unusable."""
        ...


class UsageSink(Protocol):
    """The sessions module's record of the model requests a run reported."""

    async def record_run_requests(self, run_id: str, export: object) -> None:
        """Keep the requests in a run's telemetry export; `BadRequestError` for a bad export."""
        ...


class RunControl(Protocol):
    """The runs module, seen from the broker."""

    async def active_run_ids(self, ids: Sequence[str]) -> set[str]:
        """Which of the runs are still active."""
        ...

    async def halt_run(self, run_id: str, reason: str) -> None:
        """Stop the run with the sentence as its reason."""
        ...
