"""The runs service: the one public API of the module.

Other modules import this package and `code_factory.runs.models`, nothing else.
"""

from collections.abc import Sequence

from code_factory.platform.errors import BadRequestError
from code_factory.runs.models import Run
from code_factory.runs.repository import RunRepository
from code_factory.runs.service.ending import Ending
from code_factory.runs.service.permissions import PermissionService
from code_factory.runs.service.previews import PreviewService
from code_factory.runs.service.starting import HALTED, Starting


class RunService(Starting, Ending):
    """Starting, stopping and reading agent runs."""

    async def import_completed(self, runs: Sequence[Run]) -> None:
        """Import settled history without starting processes or replaying exit effects."""
        if any(
            run.exit_code is None
            or run.ended_at is None
            or run.settled_at is None
            or not run.started_at <= run.ended_at <= run.settled_at
            for run in runs
        ):
            raise BadRequestError("imported agent runs must be complete and settled")
        async with self._uow() as session:
            repository = RunRepository(session)
            for run in runs:
                await repository.insert(run)


__all__ = ["HALTED", "PermissionService", "PreviewService", "RunService"]
