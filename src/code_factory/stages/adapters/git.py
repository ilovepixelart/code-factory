"""git at the edge: the reads the review hold makes of a branch head, each a short-lived child.

A child runs with the repository variables of this process removed, under a timeout, and is always
reaped (`platform.process.run_process`). One semaphore bounds the children of the module. A read
that fails, times out or prints more than the cap is `None`: the rule then holds.
"""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from code_factory.platform.errors import UnavailableError
from code_factory.platform.process import MIB, run_process
from code_factory.platform.programs import TEMPORARY_FOLDERS, child_environment, find_program

TIMEOUT_S = 30.0
OUTPUT_CAP = 8 * MIB
CONCURRENCY = 4
SUBMODULES = "--ignore-submodules=none"
FIXED_ENVIRONMENT = {"GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}


def clean_environment() -> dict[str, str]:
    """This process's environment without the variables that name a repository, settings fixed."""
    return {**child_environment(os.environ), **FIXED_ENVIRONMENT}


@dataclass(frozen=True)
class GitResult:
    """What a git command printed and how it ended."""

    code: int
    text: str


class GitRunner:
    """Runs git in a repository: bounded in time, output and concurrency."""

    def __init__(
        self,
        *,
        timeout: float = TIMEOUT_S,
        concurrency: int = CONCURRENCY,
        program: Path | None = None,
    ) -> None:
        self._timeout = timeout
        self._slots = asyncio.Semaphore(concurrency)
        self._program = program

    async def _git(self) -> Path | None:
        """The git to start, found once in a folder only root or the user can write."""
        if self._program is None:
            self._program = await find_program("git", TEMPORARY_FOLDERS)
        return self._program

    async def run(self, root: Path, *args: str) -> GitResult | None:
        """The command's exit code and output; `None` when it did not run to its end."""
        try:
            program = await self._git()
            if program is None:
                return None
            argv = [str(program), "--no-optional-locks", "-C", str(root), *args]
            async with self._slots:
                done = await run_process(
                    argv,
                    env=clean_environment(),
                    timeout_s=self._timeout,
                    output_cap=OUTPUT_CAP,
                )
        except UnavailableError:
            return None
        if done.code is None:
            return None
        return GitResult(done.code, done.stdout.decode("utf-8", errors="replace"))

    async def text(self, root: Path, *args: str) -> str | None:
        """The output of a command that exited 0; `None` when it failed."""
        found = await self.run(root, *args)
        return found.text if found is not None and found.code == 0 else None


class GitDiffReader:
    """The reads of the repository at `root` that the review hold makes of a branch head."""

    def __init__(self, root: Path, git: GitRunner | None = None) -> None:
        self._root = root
        self._git = git or GitRunner()

    async def default_base(self) -> str | None:
        """The ref work forks from: the remote's default branch when tracked, else the local one."""
        named = await self._git.text(
            self._root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"
        )
        names = [named.strip().removeprefix("origin/")] if named is not None else []
        for branch in [*names, "main", "master"]:
            for ref in (f"refs/remotes/origin/{branch}", f"refs/heads/{branch}"):
                found = await self._git.text(self._root, "rev-parse", "--verify", "--quiet", ref)
                if found is not None and found.strip():
                    return ref
        return None

    async def fork_point(self, head: str) -> str | None:
        """The commit `head` forked from the default branch; `None` when git cannot say."""
        base = await self.default_base()
        if base is None:
            return None
        found = await self._git.text(
            self._root,
            "-c",
            "core.commitGraph=false",
            "merge-base",
            "--end-of-options",
            base,
            head,
        )
        return None if found is None else found.strip() or None

    async def diff(self, base: str, head: str, form: str) -> str | None:
        """`git diff <form> -z` of what `head` changes since it forked from `base`."""
        return await self._git.text(
            self._root,
            "diff",
            form,
            "-z",
            "--no-renames",
            SUBMODULES,
            "--end-of-options",
            f"{base}...{head}",
        )

    async def same_code(self, source: str, target: str) -> bool:
        """Whether what a review read at `source` is what merges at `target`.

        `target` is `source` or comes after it on one line, with no merge between, and the two
        differ in no file. A merge between them can keep the tree and still change what merges, by
        taking the default branch in without its changes; a submodule's commit counts as code.
        """
        if source == "":
            return False
        if source == target:
            return True
        ancestor = await self._git.run(
            self._root, "merge-base", "--is-ancestor", "--end-of-options", source, target
        )
        if ancestor is None or ancestor.code != 0:
            return False
        merges = await self._git.text(
            self._root, "rev-list", "--merges", "--end-of-options", f"{source}..{target}"
        )
        if merges is None or merges.strip():
            return False
        same = await self._git.run(
            self._root, "diff", "--quiet", SUBMODULES, "--end-of-options", source, target
        )
        return same is not None and same.code == 0
