"""Production error reports: one bug ticket per fingerprint, each repeat counted on it."""

from datetime import datetime

from code_factory.hooks.models import ErrorReported
from code_factory.hooks.ports import NewBug
from code_factory.hooks.rules.error_report import DEFAULT_WATCH_DAYS, normalise, release_tie
from code_factory.hooks.service.base import Collaborators
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError

REPORTER = "error report"


class ReportMixin(Collaborators):
    """`code-factory error`."""

    async def report_error(self, repository: str, report: object, now: datetime) -> ErrorReported:
        """File the report as a bug ticket, or count it on the ticket its fingerprint already has.

        `BadRequestError` for a report with no one-line fingerprint, `NotFoundError` for an
        untracked repository. The ticket's own creation was the first report, so the second is
        counted 2.
        """
        fields = normalise(report)
        if isinstance(fields, str):
            raise BadRequestError(fields)
        if not await self._ports.repositories.exists(repository):
            msg = f"no tracked repository is named {repository}"
            raise NotFoundError(msg)
        source = f"error:{fields.fingerprint}"
        if (known := await self._ports.tickets.by_source(repository, source)) is not None:
            return await self._counted(known.id, fields.message)
        days = await self._ports.releases.watch_days(repository)
        tie = release_tie(
            await self._ports.releases.published(repository),
            fields.release,
            now.timestamp(),
            DEFAULT_WATCH_DAYS if days is None else days,
        )
        description = (
            f"Reported by code-factory error with the fingerprint {fields.fingerprint}.\n\n"
            f"{fields.message}"
        ).strip()
        if tie is not None:
            description = f"{description}\n\n{tie.paragraph}"
        bug = NewBug(
            repository=repository,
            title=fields.title or f"Production error {fields.fingerprint}",
            description=description,
            source=source,
            caused_by=[] if tie is None else tie.caused_by,
        )
        try:
            created = await self._ports.tickets.create_bug(bug)
        except ConflictError:
            # A concurrent report filed it first: this one is a repeat.
            known = await self._ports.tickets.by_source(repository, source)
            if known is None:
                raise
            return await self._counted(known.id, fields.message)
        return ErrorReported(ticket_id=created, count=1, created=True)

    async def _counted(self, ticket_id: str, message: str) -> ErrorReported:
        earlier = await self._ports.tickets.reports(ticket_id)
        await self._ports.tickets.record(ticket_id, "reported", {"message": message}, REPORTER)
        return ErrorReported(ticket_id=ticket_id, count=earlier + 2, created=False)
