"""The release service: drafting, editing and publishing notes, and which release named a ticket.

Each method is one unit of work in its own session; `by` is the actor, logged.

The tag itself (git, the gate pass) is the commands module's use case over this service:
`record_tag_commit` before the push, `record_tagged` after it.
"""

import builtins
import logging
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.releases import rules
from code_factory.releases.models import ReleaseNaming, ReleaseState, ReleaseTicket, ReleaseView
from code_factory.releases.repository import ReleaseRepository
from code_factory.releases.tables import ReleaseRow
from code_factory.tickets.models import Column, TicketFilter
from code_factory.tickets.service import TicketService, utc_now

TICKET_PREFIX = "CF"
_log = logging.getLogger(__name__)


def _not_found(repository: str, version: str) -> NotFoundError:
    return NotFoundError(
        f"no release {version} of {repository}: draft it with code-factory release draft {version}"
    )


def _view(row: ReleaseRow, tickets: Iterable[str]) -> ReleaseView:
    return ReleaseView(
        repository=row.repository,
        version=row.version,
        state=rules.state_of(row.published_at, row.tagged_at),
        notes=row.notes,
        drafted_at=row.drafted_at,
        published_at=row.published_at,
        tag_commit=row.tag_commit,
        tagged_at=row.tagged_at,
        tickets=sorted(tickets, key=rules.ticket_order),
    )


class ReleaseService:
    """Releases of the tracked repositories."""

    def __init__(
        self,
        uow: UnitOfWork,
        tickets: TicketService,
        clock: Callable[[], datetime] = utc_now,
        prefix: str = TICKET_PREFIX,
    ) -> None:
        self._uow = uow
        self._tickets = tickets
        self._clock = clock
        self._prefix = prefix

    @staticmethod
    def is_version(text: str) -> bool:
        """Whether `text` is `MAJOR.MINOR.PATCH` of decimal numbers."""
        return rules.is_version(text)

    @staticmethod
    def newest_tag(names: Iterable[str]) -> str | None:
        """The highest release tag `v<MAJOR.MINOR.PATCH>` of `names`, by its numbers."""
        return rules.newest_release(names)

    async def draft(self, repository: str, version: str, *, by: str) -> ReleaseView:
        """Draft the notes of `version` from the repository's merged tickets no release names.

        A version drafted before is a `ConflictError`: a released version is immutable.
        """
        _check_repository(repository)
        rules.check_version(version)
        merged = await self._tickets.list(
            TicketFilter(repository=repository, column=Column.MERGED, archived=None)
        )
        async with self._uow() as session:
            releases = ReleaseRepository(session)
            named = await releases.named_in_published(repository)
            listed = [
                ReleaseTicket(id=ticket.id, title=ticket.title, kind=ticket.type)
                for ticket in sorted(merged, key=lambda ticket: ticket.number)
                if ticket.id not in named
            ]
            notes = rules.release_notes(version, listed)
            row = await releases.insert_draft(repository, version, notes, self._clock())
            if row is None:
                msg = f"{version} exists; a released version is immutable, draft the next one"
                raise ConflictError(msg)
            view = _view(row, [])
        _log.info("%s drafted release %s of %s", by, version, repository)
        return view

    async def edit_notes(
        self, repository: str, version: str, notes: str, *, by: str
    ) -> ReleaseView:
        """Replace a draft's notes; a published release's notes are final."""
        rules.check_notes(notes)
        async with self._uow() as session:
            releases = ReleaseRepository(session)
            row = await releases.update_notes(repository, version, notes)
            if row is None:
                raise await self._refusal(releases, repository, version, "notes")
            view = _view(row, [])
        _log.info("%s edited the notes of release %s of %s", by, version, repository)
        return view

    async def publish(self, repository: str, version: str, *, by: str) -> ReleaseView:
        """Publish a draft: its notes become final and the tickets they name leave the board."""
        async with self._uow() as session:
            releases = ReleaseRepository(session)
            current = await releases.find(repository, version, for_update=True)
            if current is None:
                raise _not_found(repository, version)
            ids = rules.ticket_ids_in(current.notes, self._prefix)
            row = await releases.publish(repository, version, self._clock(), ids)
            if row is None:
                raise await self._refusal(releases, repository, version, "publish")
            view = _view(row, ids)
        _log.info("%s published release %s of %s", by, version, repository)
        return view

    async def get(self, repository: str, version: str) -> ReleaseView:
        """The release `version`; `NotFoundError` when it was never drafted."""
        async with self._uow() as session:
            found = await ReleaseRepository(session).with_tickets(repository, version)
        if not found:
            raise _not_found(repository, version)
        return _view(*found[0])

    async def list(self, repository: str | None = None) -> builtins.list[ReleaseView]:
        """The releases of one repository, or of all: by repository, newest version first."""
        async with self._uow() as session:
            found = await ReleaseRepository(session).with_tickets(repository)
        found.sort(key=lambda item: rules.version_key(item[0].version), reverse=True)
        found.sort(key=lambda item: item[0].repository)
        return [_view(row, ids) for row, ids in found]

    async def newest(self, repository: str) -> ReleaseView | None:
        """The tagged release with the highest version; drafts and untagged ones never count."""
        tagged = [
            release
            for release in await self.list(repository)
            if release.state is ReleaseState.TAGGED
        ]
        return tagged[0] if tagged else None

    async def naming(self, refs: Sequence[tuple[str, str]]) -> dict[tuple[str, str], ReleaseNaming]:
        """The release that named each `(repository, ticket id)`, for published releases only.

        A ticket two releases name belongs to the one published first. One statement whatever
        the number of refs.
        """
        if not refs:
            return {}
        async with self._uow() as session:
            found = await ReleaseRepository(session).naming(refs)
        named: dict[tuple[str, str], ReleaseNaming] = {}
        for repository, ticket_id, version, published_at in found:
            named.setdefault(
                (repository, ticket_id), ReleaseNaming(version=version, published_at=published_at)
            )
        return named

    async def record_tag_commit(
        self, repository: str, version: str, commit: str, *, by: str
    ) -> ReleaseView:
        """Record the commit the release's tag is made on, before the tag is pushed.

        Recording the same commit again changes nothing; another commit is refused, so a tag
        that may already be on origin never moves.
        """
        rules.check_commit(commit)
        async with self._uow() as session:
            releases = ReleaseRepository(session)
            row = await releases.set_tag_commit(repository, version, commit)
            if row is None:
                raise await self._refusal(releases, repository, version, "tag", commit)
            named = await releases.tickets_of([row.id])
        _log.info("%s recorded tag commit %s of release %s of %s", by, commit, version, repository)
        return _view(row, named[row.id])

    async def record_tagged(self, repository: str, version: str, *, by: str) -> ReleaseView:
        """Record that the tag reached origin; the first time recorded stands."""
        async with self._uow() as session:
            releases = ReleaseRepository(session)
            row = await releases.set_tagged(repository, version, self._clock())
            if row is None:
                raise await self._refusal(releases, repository, version, "tagged")
            named = await releases.tickets_of([row.id])
        _log.info("%s recorded release %s of %s as tagged", by, version, repository)
        return _view(row, named[row.id])

    @staticmethod
    async def _refusal(
        releases: ReleaseRepository, repository: str, version: str, action: str, commit: str = ""
    ) -> NotFoundError | ConflictError:
        """Why a guarded update touched no row: no such release, or the state forbids it."""
        row = await releases.find(repository, version)
        if row is None:
            return _not_found(repository, version)
        match action:
            case "notes":
                return ConflictError(f"{version} is published: its notes are final")
            case "publish":
                return ConflictError(f"{version} is published already")
            case "tag" if row.published_at is None:
                return ConflictError(f"{version} is a draft: publish it first")
            case "tag":
                return ConflictError(
                    f"{version} is tagged on {(row.tag_commit or '')[:7]}, not on {commit[:7]}"
                )
            case _:
                return ConflictError(f"{version} has no tag commit recorded: record it first")


def _check_repository(repository: str) -> None:
    if not repository.strip():
        raise BadRequestError("a release needs a repository: name the tracked repository")
