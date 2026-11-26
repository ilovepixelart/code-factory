"""The checks module's public API: runs, verdicts, main's checks, verification, runner claims."""

from code_factory.checks.service.base import CheckDeps, CheckOptions, utc_now
from code_factory.checks.service.upkeep import UpkeepMixin


class CheckService(UpkeepMixin):
    """Runs the repository's checks command, keeps its verdicts and hands checks to runners.

    No transaction is open across a subprocess or a git call: rows are written before and after
    in short units of work. Errors are the platform's classes with the sentences a person reads.
    """


__all__ = ["CheckDeps", "CheckOptions", "CheckService", "utc_now"]
