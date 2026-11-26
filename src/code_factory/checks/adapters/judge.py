"""What a checks run judges: the commit checked out in a tree and a name for its state.

The tree is read through its git folder named on the command line, never through the `.git` file
inside it: the checks run in that tree and could rewrite the file to point git at a repository of
their own, so that a tree that changed reads as the one it began as.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from code_factory.checks.rules import tree_name
from code_factory.platform.errors import UnavailableError
from code_factory.platform.process import run_process
from code_factory.platform.programs import child_environment, find_program

READ_TIMEOUT_S = 60.0
OUTPUT_CAP = 32 * 1024 * 1024


@dataclass(frozen=True)
class TreeState:
    """The commit checked out in a tree and a digest of the commit, its status and its changes."""

    head: str
    name: str
    tracked: str  # the commit and its tracked changes, untracked files left out
    tracked_clean: bool  # no tracked file differs from the commit


class TreeJudge:
    """Reads the state of a tree with the trusted git."""

    def __init__(self, places: Callable[[], Sequence[Path]]) -> None:
        self._places = places

    async def read(self, git_dir: Path, tree: Path, environment: dict[str, str]) -> TreeState:
        """The state of `tree` whose git folder is `git_dir`.

        Raises `UnavailableError` when git cannot be run or answers nothing: a tree that cannot be
        read is no verdict.
        """
        program = await find_program("git", self._places())
        if program is None:
            msg = "git is not on a trusted PATH: the checked tree cannot be named"
            raise UnavailableError(msg)
        env = child_environment({**environment, "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"})
        base = [
            str(program),
            f"--git-dir={git_dir}",
            f"--work-tree={tree}",
            "-c",
            "core.fsmonitor=false",
        ]
        head = (await self._run(base, ["rev-parse", "--verify", "HEAD"], tree, env)).strip()
        status = await self._run(base, ["status", "--porcelain", "-uall"], tree, env)
        changes = await self._run(base, ["diff-index", "-p", "HEAD"], tree, env)
        return TreeState(
            head=head,
            name=tree_name(head, status, changes),
            tracked=tree_name(head, "", changes),
            tracked_clean=changes == "",
        )

    @staticmethod
    async def _run(
        base: Sequence[str], args: Sequence[str], tree: Path, env: dict[str, str]
    ) -> str:
        done = await run_process(
            [*base, *args], cwd=tree, env=env, timeout_s=READ_TIMEOUT_S, output_cap=OUTPUT_CAP
        )
        if done.code != 0 or done.truncated:
            msg = f"git {args[0]} could not read the checked tree"
            raise UnavailableError(msg)
        return done.stdout.decode(errors="replace")
