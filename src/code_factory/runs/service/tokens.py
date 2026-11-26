"""Issue a run's board token and release its credentials and private files at settlement."""

from datetime import timedelta
from pathlib import Path

from code_factory.auth.service import AuthService
from code_factory.broker.service import BrokerService
from code_factory.platform.services import Services
from code_factory.runs.adapters import files
from code_factory.runs.service.codex import run_folder


class TokensAdapter:
    """The credential lifecycle of one run."""

    def __init__(self, services: Services, state: Path) -> None:
        self._services = services
        self._state = state

    async def issue(
        self, run_id: str, ticket_id: str | None, stage: str, repository: str, lifetime_s: int
    ) -> str:
        """A token for one run; the value is shown once."""
        issued = await self._services.get(AuthService).issue_run_token(
            run_id=run_id,
            ticket_id=ticket_id,
            stage=stage,
            repository=repository,
            lifetime=timedelta(seconds=lifetime_s),
        )
        return issued.token.get_secret_value()

    async def revoke(self, run_id: str) -> None:
        """End every token of the run and remove its private configuration."""
        await self._services.get(AuthService).revoke_run(run_id)
        await self._services.get(BrokerService).end_run(run_id)
        await files.remove_run_folder(run_folder(self._state, run_id))
