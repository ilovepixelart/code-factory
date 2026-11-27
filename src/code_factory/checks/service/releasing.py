"""`[release] verify`: run hourly while the newest release is inside its window, file one bug."""

import logging
from pathlib import Path

from code_factory.checks.adapters import base_environment
from code_factory.checks.models import ReleaseRef, VerifyRecord
from code_factory.checks.rules import log_tail, verify_bug, verify_due
from code_factory.checks.service.base import ACTOR
from code_factory.checks.service.command import limit_seconds
from code_factory.checks.service.config import RunConfig
from code_factory.checks.service.mainchecks import MainMixin
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.platform.process import run_logged
from code_factory.platform.text import masked
from code_factory.tickets.models import NewTicket

logger = logging.getLogger(__name__)
VERIFY_SUBJECT = "verify"
NO_COMMAND = "no [release] verify command in .code-factory/config.toml"


class ReleasingMixin(MainMixin):
    """Verification of the newest release."""

    async def due_verify(self, repository: str) -> ReleaseRef | None:
        """The newest release when its verification is due now and none of it is running."""
        if repository in self._verifying:
            return None
        return await self._due_verification(repository, await self._config(repository))

    async def _due_verification(self, repository: str, config: RunConfig) -> ReleaseRef | None:
        if config.verify in (None, "") or config.watch_days == 0:
            return None
        newest = await self.newest_release(repository)
        if newest is None:
            return None
        async with self._db() as store:
            last = await store.records.verify_runs(repository, 1)
        due = verify_due(
            config.verify,
            newest,
            self._now(),
            last[0].at if last else None,
            config.watch_days,
        )
        return newest if due else None

    async def newest_release(self, repository: str) -> ReleaseRef | None:
        """The newest tagged release, as a verification reads it."""
        release = await self._deps.releases.newest(repository)
        if release is None:
            return None
        when = release.tagged_at or release.published_at or release.drafted_at
        return ReleaseRef(version=release.version, at=when, tickets=list(release.tickets))

    async def verify_records(self, repository: str, limit: int = 20) -> list[VerifyRecord]:
        """The newest verification runs of the repository, newest first."""
        async with self._db() as store:
            return await store.records.verify_runs(repository, limit)

    async def verify(
        self, repository: str, release: ReleaseRef, *, scheduled: bool = False
    ) -> VerifyRecord:
        """Run `[release] verify` in the main checkout and record it.

        A failure files one bug per release, or counts on the open one of an earlier failure.
        """
        config = await self._config(repository)
        if config.verify is None:
            raise BadRequestError(NO_COMMAND)
        if repository in self._verifying:
            msg = f"the verification of {repository} is running already"
            raise ConflictError(msg)
        self._verifying.add(repository)
        try:
            async with (
                self._slots,
                self._deps.verify_claim(f"checks:release:{repository}") as acquired,
            ):
                if not acquired:
                    msg = f"the verification of {repository} is running already"
                    raise ConflictError(msg)
                if scheduled and await self._due_verification(repository, config) != release:
                    msg = f"the verification of {repository} is no longer due"
                    raise ConflictError(msg)
                return await self._verify(repository, release, config.verify, config.timeout)
        finally:
            self._verifying.discard(repository)

    async def _verify(
        self, repository: str, release: ReleaseRef, command: str, configured: int | None
    ) -> VerifyRecord:
        root = await self._root(repository)
        await self._policy.refresh()
        second = int(self._now().timestamp())
        log = self._logs.path_for(repository, VERIFY_SUBJECT, second)
        env = await base_environment(self._policy.places())
        ran = await run_logged(
            command, cwd=root, log=log, env=env, limit_s=limit_seconds(configured)
        )
        code = -1 if ran is None else ran
        ticket = ""
        if code != 0:
            ticket = await self._report_failure(repository, release, command, (code, log))
        async with self._db() as store:
            return await store.records.add_verify(
                repository, release.version, self._now(), (code, str(log), ticket)
            )

    async def _open_bug(self, repository: str, release: str) -> str | None:
        """The bug an earlier failing run of the release filed, while it is open."""
        async with self._db() as store:
            earlier = await store.records.verify_runs(repository, 200)
        found = next((r.ticket for r in earlier if r.release == release and r.ticket), None)
        if found is None:
            return None
        try:
            bug = await self._deps.tickets.get(found)
        except NotFoundError:
            return None
        return None if bug.archived or bug.merged else bug.id

    async def _report_failure(
        self, repository: str, release: ReleaseRef, command: str, outcome: tuple[int, Path]
    ) -> str:
        code, log = outcome
        tickets = self._deps.tickets
        open_bug = await self._open_bug(repository, release.version)
        if open_bug is not None:
            data: dict[str, object] = {"exit_code": code, "log": str(log)}
            await tickets.record_activity(open_bug, "verify_failed", data, by=ACTOR)
            return open_bug
        text = await self._logs.text_of(log) or ""
        draft = verify_bug(release, command, code, str(log), masked(log_tail(text)))
        bug = await tickets.create(
            NewTicket(
                repository=repository,
                title=draft.title,
                type="bug",
                labels=draft.labels,
                priority="high",
                caused_by=draft.caused_by,
                description=draft.description,
            ),
            by=ACTOR,
        )
        return bug.id
