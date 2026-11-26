"""Queries over main's record and the release verification runs."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.checks.models import MainRecord, VerifyRecord
from code_factory.checks.tables import CheckMainRecordRow, CheckVerifyRunRow

KEPT_VERIFY_RUNS = 200


def _main(row: CheckMainRecordRow) -> MainRecord:
    return MainRecord(
        repository=row.repository,
        commit=row.commit,
        exit_code=row.exit_code,
        log=row.log_path,
        at=row.at,
        step=row.step,
        passed=row.passed,
        broken_by=row.broken_by,
        searched=row.searched,
        reason=row.reason,
    )


def _verify(row: CheckVerifyRunRow) -> VerifyRecord:
    return VerifyRecord(
        id=row.id,
        repository=row.repository,
        release=row.release,
        at=row.at,
        exit_code=row.exit_code,
        log=row.log_path,
        ticket=row.ticket_id,
    )


class RecordStore:
    """Main's record and the verification runs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def main(self, repository: str) -> MainRecord | None:
        """The latest run on the repository's default branch."""
        row = await self._session.get(CheckMainRecordRow, repository)
        return None if row is None else _main(row)

    async def all_main(self) -> list[MainRecord]:
        """Every repository's latest run on its default branch."""
        rows = await self._session.execute(
            select(CheckMainRecordRow).order_by(CheckMainRecordRow.repository)
        )
        return [_main(row) for row in rows.scalars()]

    async def put_main(self, record: MainRecord) -> None:
        """Keep `record` as the repository's latest run."""
        values = {
            "repository": record.repository,
            "commit": record.commit,
            "exit_code": record.exit_code,
            "log_path": record.log,
            "at": record.at,
            "step": record.step,
            "passed": record.passed,
            "broken_by": record.broken_by,
            "searched": record.searched,
            "reason": record.reason,
        }
        statement = insert(CheckMainRecordRow).values(**values)
        await self._session.execute(
            statement.on_conflict_do_update(index_elements=["repository"], set_=values)
        )

    async def add_verify(
        self,
        repository: str,
        release: str,
        at: datetime,
        outcome: tuple[int, str, str],
    ) -> VerifyRecord:
        """Insert a run (`outcome` is exit code, log path, bug id) and keep the newest 200."""
        code, log, ticket = outcome
        row = CheckVerifyRunRow(
            repository=repository,
            release=release,
            at=at,
            exit_code=code,
            log_path=log,
            ticket_id=ticket,
        )
        self._session.add(row)
        await self._session.flush()
        newest = (
            select(CheckVerifyRunRow.id)
            .where(CheckVerifyRunRow.repository == repository)
            .order_by(CheckVerifyRunRow.id.desc())
            .limit(KEPT_VERIFY_RUNS)
        )
        await self._session.execute(
            delete(CheckVerifyRunRow).where(
                CheckVerifyRunRow.repository == repository,
                CheckVerifyRunRow.id.not_in(newest),
            )
        )
        return _verify(row)

    async def verify_runs(self, repository: str, limit: int) -> list[VerifyRecord]:
        """The newest runs of the repository, newest first."""
        statement = (
            select(CheckVerifyRunRow)
            .where(CheckVerifyRunRow.repository == repository)
            .order_by(CheckVerifyRunRow.id.desc())
            .limit(limit)
        )
        return [_verify(row) for row in (await self._session.execute(statement)).scalars()]
