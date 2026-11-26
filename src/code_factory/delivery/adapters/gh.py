"""`gh`, the one way delivery talks to GitHub: argv only, bounded, merges in one shape only."""

import asyncio
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from code_factory.platform.errors import UnavailableError
from code_factory.platform.process import run_process

TIMEOUT_S = 60.0
OUTPUT_CAP = 2 << 20
READS = 4
_PASSED_ON = ("PATH", "HOME", "GH_TOKEN", "GH_HOST", "GH_CONFIG_DIR", "XDG_CONFIG_HOME", "LANG")
_QUIET = {
    "GIT_TERMINAL_PROMPT": "0",
    "GH_PROMPT_DISABLED": "1",
    "NO_COLOR": "1",
    "GH_NO_UPDATE_NOTIFIER": "1",
    "GH_PAGER": "cat",
}
_MERGE_FLAGS = ("--admin", "--auto", "--squash", "--rebase", "--delete-branch", "--force")
MERGE_ARGC = 6
_WRITES = {("pr", "create"), ("pr", "merge"), ("pr", "edit"), ("pr", "comment"), ("api",)}


class ForbiddenCallError(ValueError):
    """An argv delivery never runs."""


@dataclass(frozen=True)
class GhResult:
    """What one call answered."""

    ok: bool
    stdout: str
    stderr: str

    @property
    def reason(self) -> str:
        """The failure as one line."""
        text = (self.stderr or self.stdout).strip()
        return text.splitlines()[-1] if text else "gh failed without a word"


def guard(argv: Sequence[str]) -> None:
    """Refuse any merge but `pr merge <url> --merge --match-head-commit <sha>`."""
    if tuple(argv[:2]) != ("pr", "merge"):
        return
    if any(flag in argv for flag in _MERGE_FLAGS):
        msg = f"refused gh argv: {' '.join(argv)}"
        raise ForbiddenCallError(msg)
    shape = len(argv) == MERGE_ARGC and argv[3] == "--merge" and argv[4] == "--match-head-commit"
    if not shape or argv[2].startswith("-") or argv[5].startswith("-"):
        msg = f"refused gh argv: {' '.join(argv)}"
        raise ForbiddenCallError(msg)


class GhRunner:
    """Runs `gh` in a repository root with a quiet, bounded environment."""

    def __init__(self, program: str = "gh", timeout_s: float = TIMEOUT_S) -> None:
        self._program = program
        self._timeout_s = timeout_s
        self._reads = asyncio.Semaphore(READS)
        self._writes: dict[Path, asyncio.Lock] = {}

    def _env(self) -> dict[str, str]:
        env = {name: os.environ[name] for name in _PASSED_ON if name in os.environ}
        return env | _QUIET

    async def run(self, root: Path, argv: Sequence[str], stdin: bytes | None = None) -> GhResult:
        """Run `gh <argv>` in `root`; `UnavailableError` when gh is missing or does not answer."""
        guard(argv)
        del stdin  # gh reads no input in the calls delivery makes
        write = tuple(argv[:2]) in _WRITES or tuple(argv[:1]) in _WRITES
        lock = self._writes.setdefault(root, asyncio.Lock()) if write else self._reads
        async with lock:
            result = await run_process(
                [self._program, *argv],
                cwd=root,
                env=self._env(),
                timeout_s=self._timeout_s,
                output_cap=OUTPUT_CAP,
            )
        if result.timed_out:
            msg = f"gh did not answer within {self._timeout_s:g} s"
            raise UnavailableError(msg)
        out = result.stdout.decode(errors="replace")
        err = result.stderr.decode(errors="replace")
        return GhResult(ok=result.code == 0 and not result.truncated, stdout=out, stderr=err)

    async def run_json(self, root: Path, argv: Sequence[str]) -> Any:  # noqa: ANN401  # gh's JSON
        """The parsed answer, or `None` when gh failed or answered something else."""
        answer = await self.run(root, argv)
        if not answer.ok:
            return None
        try:
            return json.loads(answer.stdout or "null")
        except json.JSONDecodeError:
            return None
