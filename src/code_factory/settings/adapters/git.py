"""git at the edge: the few reads the settings rules need, each a short-lived child process.

A child runs with the repository variables of this process removed, under a timeout, and is always
reaped. One semaphore bounds the children of this process.
"""

import asyncio
import os
from asyncio.subprocess import DEVNULL, PIPE, Process
from dataclasses import dataclass
from pathlib import Path

TIMEOUT_S = 15.0
GRACE_S = 2.0
OUTPUT_LIMIT = 1024 * 1024
CONCURRENCY = 4
# Fully qualified: a short name is looked up among tags first, so a tag or a branch named `main`
# would stand in for the base branch.
BASE_REFS = ("refs/remotes/origin/HEAD", "refs/heads/main", "refs/heads/master")


def _short(ref: str) -> str:
    return ref.removeprefix("refs/remotes/").removeprefix("refs/heads/")


_REPOSITORY_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
)
_CHUNK = 64 * 1024


@dataclass(frozen=True)
class Fork:
    """Where HEAD forked from the base branch: the fork point, HEAD, and the paths changed since.

    Each is None when git could not say.
    """

    base: str | None
    head: str | None
    changed: tuple[str, ...] | None


class GitFacts:
    """Reads of one repository's tracked files, history and fork point."""

    def __init__(
        self,
        *,
        executable: str = "git",
        timeout: float = TIMEOUT_S,
        grace: float = GRACE_S,
        output_limit: int = OUTPUT_LIMIT,
    ) -> None:
        self._executable = executable
        self._timeout = timeout
        self._grace = grace
        self._limit = output_limit
        self._slots = asyncio.Semaphore(CONCURRENCY)

    async def _read_capped(self, process: Process) -> bytes | None:
        """The standard output, or None when it is longer than the cap."""
        assert process.stdout is not None  # noqa: S101  # stdout=PIPE
        chunks: list[bytes] = []
        size = 0
        while chunk := await process.stdout.read(_CHUNK):
            size += len(chunk)
            if size > self._limit:
                return None
            chunks.append(chunk)
        return b"".join(chunks)

    async def _reap(self, process: Process) -> None:
        if process.returncode is None:
            process.terminate()
            try:
                async with asyncio.timeout(self._grace):
                    await process.wait()
            except TimeoutError:
                process.kill()
        await process.wait()
        # A reader that stopped early left the pipe paused; reading it to the end closes it.
        assert process.stdout is not None  # noqa: S101  # stdout=PIPE
        try:
            async with asyncio.timeout(self._grace):
                while await process.stdout.read(_CHUNK):
                    continue  # the pipe is read to its end so the child is not left blocked
        except TimeoutError:
            return

    async def _run(self, root: Path, *args: str) -> tuple[int, bytes] | None:
        """`(exit code, output)` of `git -C root args`.

        None when it did not finish in time, wrote too much or could not start.
        """
        env = {k: v for k, v in os.environ.items() if k not in _REPOSITORY_VARIABLES}
        async with self._slots:
            try:
                process = await asyncio.create_subprocess_exec(
                    self._executable,
                    "--no-optional-locks",
                    "-C",
                    str(root),
                    *args,
                    stdin=DEVNULL,
                    stdout=PIPE,
                    stderr=DEVNULL,
                    env=env,
                )
            except OSError, ValueError:
                return None
            try:
                async with asyncio.timeout(self._timeout):
                    output = await self._read_capped(process)
                    if output is None:
                        return None
                    code = await process.wait()
            except TimeoutError:
                return None
            finally:
                await self._reap(process)
        return code, output

    async def _lines(self, root: Path, *args: str) -> list[str] | None:
        """The NUL- or newline-separated output of a successful command, else None."""
        result = await self._run(root, *args)
        if result is None or result[0] != 0:
            return None
        text = result[1].decode("utf-8", errors="replace")
        return [item for item in text.split("\0" if "\0" in text else "\n") if item]

    async def tracked(self, root: Path, patterns: list[str]) -> list[str]:
        """The tracked files matching a `**/name` pattern, relative to `root`; none outside one."""
        found = await self._lines(
            root, "ls-files", "-z", "--", *(f":(glob){pattern}" for pattern in patterns)
        )
        return [] if found is None else found

    async def grep_exists(self, root: Path, pattern: str, paths: tuple[str, ...]) -> bool:
        """Whether a tracked file at one of `paths` holds the fixed text `pattern`."""
        result = await self._run(root, "grep", "-l", "-F", "-e", pattern, "--", *paths)
        return result is not None and result[0] == 0 and bool(result[1].strip())

    async def _commit(self, root: Path, ref: str) -> str | None:
        found = await self._lines(
            root, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref}^{{commit}}"
        )
        return found[0] if found is not None and found else None

    async def _branch_commit(self, root: Path, ref: str) -> str | None:
        """The commit of the fully qualified `ref` itself: no tag or other namespace stands in."""
        found = await self._lines(root, "show-ref", "--verify", "--hash", "--", ref)
        return await self._commit(root, found[0]) if found is not None and found else None

    async def fork(self, root: Path, base_ref: str | None) -> Fork:
        """Where HEAD forked from `base_ref`, or from `origin/HEAD`, `main` or `master`.

        Nothing known when no such base exists or HEAD has no commit.
        """
        head = await self._commit(root, "HEAD")
        base = None
        for ref in (base_ref,) if base_ref is not None else BASE_REFS:
            tip = await (
                self._branch_commit(root, ref) if base_ref is None else self._commit(root, ref)
            )
            merged = None
            if tip is not None and head is not None:
                found = await self._lines(
                    root, "-c", "core.commitGraph=false", "merge-base", head, tip
                )
                merged = found[0] if found is not None and found else None
            if merged is not None:
                base = merged
                break
        if base is None:
            return Fork(base=None, head=head, changed=None)
        # Against the working tree, so an edit not yet committed counts as a change.
        changed = await self._lines(root, "diff", "--name-only", "-z", base, "--")
        return Fork(base=base, head=head, changed=None if changed is None else tuple(changed))

    async def show_on_base(self, root: Path, path: str) -> tuple[str, str] | None:
        """`(base ref, text)` of the file `path` as the base branch commits it.

        The base is the first of `origin/HEAD`, `main` and `master` (as branches, never as tags)
        that holds a commit, read by the commit's id, so neither a branch's own edit nor an
        uncommitted one is read. None when that commit holds no such file, `path` is not a file, or
        the text is longer than the output cap.
        """
        for ref in BASE_REFS:
            sha = await self._branch_commit(root, ref)
            if sha is None:
                continue
            result = await self._run(root, "cat-file", "blob", f"{sha}:{path}")
            if result is None or result[0] != 0:
                return None
            return _short(ref), result[1].decode("utf-8", errors="replace")
        return None

    async def toplevel(self, path: Path) -> Path | None:
        """The root of the repository holding `path`, None outside one."""
        found = await self._lines(path, "rev-parse", "--show-toplevel")
        return Path(found[0]) if found is not None and found else None

    async def main_checkout(self, path: Path) -> Path | None:
        """The main checkout of the repository holding `path`, whichever worktree `path` is in."""
        found = await self._lines(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if found is None or not found:
            return None
        common = Path(found[0])
        return common.parent if common.name == ".git" else None
