"""The checks module's public API: runs, verdicts, main's checks, verification, runner claims."""

from pathlib import Path

from code_factory.checks.service.base import CheckDeps, CheckOptions, utc_now
from code_factory.checks.service.config import run_config
from code_factory.checks.service.spec import SpecMixin
from code_factory.git.models import HookOutcome
from code_factory.platform.contained import Work


class CheckService(SpecMixin):
    """Runs the repository's checks command, keeps its verdicts and hands checks to runners.

    No transaction is open across a subprocess or a git call: rows are written before and after
    in short units of work. Errors are the platform's classes with the sentences a person reads.
    """

    async def worktree_setup(self, repository: str, tree: Path) -> HookOutcome:
        """Set up a freshly made agent clone using the main checkout's config."""
        root = await self._deps.repositories.get(repository)
        setup = run_config(await self._deps.settings.load(root)).setup
        if setup is None:
            return HookOutcome(code=0)
        await self._policy.refresh()
        log = self._opts.state_dir / "hooks" / f"{tree.name}.setup.log"
        code = await self._runner.run(
            Work.SETUP, repository, setup.command, tree, log, setup.limit_s
        )
        return HookOutcome(code=code, log=log)


__all__ = ["CheckDeps", "CheckOptions", "CheckService", "utc_now"]
