"""The stage service: the parts composed, with the pure readers other modules may not import."""

from code_factory.stages import rules
from code_factory.stages.models import LogReading, MainCheckView, PullView
from code_factory.stages.service.fixloop import FixLoop
from code_factory.stages.service.observe import Observing
from code_factory.stages.service.review import Reviewing


class StageService(Reviewing, Observing, FixLoop):
    """Which column a ticket is in, why a move is refused and what a head's verdicts say.

    Each async method is one unit of work (or reads, then writes in a second); the synchronous
    readers below need no session.
    """

    @staticmethod
    def read_log(log: str, exit_code: int | None = None) -> LogReading:
        """What a checks log says: its failing lines and tests, build failure, steps and flakes.

        `exit_code` is the exit code of the run that wrote it, when the caller has it; the reading
        comes from the log alone.
        """
        del exit_code
        return rules.read_log(log)

    @staticmethod
    def feedback_reason(pull: PullView, own: int | None) -> str:
        """What sends an open pull request back: `ci`, `review`, or empty."""
        return rules.feedback_reason(pull, own)

    @staticmethod
    def fails_on_main(
        steps: list[str], tests: list[str], main: MainCheckView, main_tests: list[str]
    ) -> str | None:
        """The step on which main failed with the same failing tests as the head's checks."""
        return rules.fails_on_main(steps, tests, main, main_tests)

    @staticmethod
    def no_verdict(code: int) -> bool:
        """Whether a checks run that exited `code` gave no verdict on the code."""
        return rules.no_verdict(code)

    @staticmethod
    def killed_run(code: int, log: str) -> bool:
        """Whether a run that exited `code` ending with `log` was killed by the system."""
        return rules.killed_run(code, log)

    @staticmethod
    def last_started_step(log: str) -> str | None:
        """The step a gate log last started: where a killed run was."""
        return rules.last_started_step(log)
