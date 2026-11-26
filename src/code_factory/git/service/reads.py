"""What git knows of a repository: facts, branches, diffs, merges, conflicts, plain reads."""

import asyncio
from datetime import datetime
from pathlib import Path

from code_factory.git.adapters.runner import DIFF_CAP, LOG_TIMEOUT_S
from code_factory.git.models import (
    DIFF_LIMIT,
    MERGE_LOG_LIMIT,
    BranchState,
    ChangesView,
    GitFacts,
    LogEntry,
    Merge,
    MergeCheck,
)
from code_factory.git.repository import GitStore
from code_factory.git.rules import digests
from code_factory.git.rules import facts as fact_rules
from code_factory.git.rules import merges as merge_rules
from code_factory.git.rules.diffs import parse_diff
from code_factory.git.service.base import GitBase
from code_factory.platform.errors import UnavailableError

_BRANCH_REFS = [
    "for-each-ref",
    "--format=%(refname) %(objectname)",
    "refs/heads/",
    "refs/remotes/origin/",
]
_LOG_FORMAT = "--format=%H%x09%P%x09%s"


def _over(command: list[str], branches: list[str]) -> list[str]:
    """`command`, the revisions, then `--`: without it git asks the work tree too."""
    return [*command, "--end-of-options", *branches, "--"]


class ReadsMixin(GitBase):
    """Reads of one repository's history."""

    async def facts(self, repository: str) -> GitFacts:
        """Five git calls whatever the number of branches; concurrent callers share one read."""
        task = self._flights.get(repository)
        if task is None:
            task = self._spawn(self._read_facts(repository))
            self._flights[repository] = task
            self._reading.add(task)
            task.add_done_callback(lambda done: self._finished(repository, done))
        return await asyncio.shield(task)

    def _finished(self, repository: str, task: asyncio.Task[GitFacts]) -> None:
        self._reading.discard(task)
        if self._flights.get(repository) is task:
            del self._flights[repository]

    def invalidate(self, repository: str) -> None:
        """Drop the read in flight so the next caller reads again."""
        self._flights.pop(repository, None)

    async def _ok_or_none(self, root: Path, args: list[str]) -> str | None:
        """A read's text; `None` when git fails or runs out of time, which makes facts unknown."""
        try:
            return await self._runner.ok(root, args, timeout_s=LOG_TIMEOUT_S)
        except UnavailableError:
            return None

    async def _read_facts(self, repository: str) -> GitFacts:
        root = await self._root(repository)
        listed = await self._ok_or_none(root, _BRANCH_REFS)
        refs = fact_rules.parse_branch_refs(listed or "")
        symbolic = await self._ok_or_none(
            root, ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"]
        )
        default = fact_rules.default_branch(symbolic, refs.local)
        branches = [default] + ([f"origin/{default}"] if default in refs.remote else [])
        absent = default not in refs.local  # an unborn default branch: its reads are empty, known

        async def read(command: list[str]) -> str | None:
            text = await self._ok_or_none(root, _over(command, branches))
            return "" if text is None and absent else text

        async with asyncio.TaskGroup() as group:
            merges = group.create_task(read(["log", "--merges", _LOG_FORMAT]))
            line = group.create_task(read(["rev-list", "--parents"]))
            log = group.create_task(read(["log", "-n", str(MERGE_LOG_LIMIT), _LOG_FORMAT]))
        texts = (merges.result(), line.result(), log.result())
        return fact_rules.build_facts(
            refs, symbolic, *(t or "" for t in texts), ok=listed is not None and None not in texts
        )

    async def branch_state(self, repository: str, branch: str) -> BranchState:
        """Tips from the facts plus one `rev-list --count`."""
        facts = await self.facts(repository)
        tip = facts.tips.get(branch, "")
        remote = facts.tips.get(f"origin/{branch}", "")
        ahead = 0
        base = fact_rules.base_tip(facts)
        if tip != "" and base is not None:
            root = await self._root(repository)
            count = await self._runner.ok(root, ["rev-list", "--count", f"{base}..{tip}"])
            ahead = int(count) if count is not None and count.isdigit() else 0
        merged = fact_rules.branch_merged(branch, facts)
        return BranchState(
            tip=tip, remote_tip=remote, ahead=ahead, merged=bool(merged), pushed=bool(remote)
        )

    async def fork_point(self, repository: str, commit: str, at: Path | None = None) -> str | None:
        """The merge base of `commit` and the base tip, ignoring a commit graph a run may forge."""
        base = fact_rules.base_tip(await self.facts(repository))
        if base is None:
            return None
        root = at or await self._root(repository)
        words = ["-c", "core.commitGraph=false", "merge-base", "--end-of-options", base, commit]
        return await self._runner.ok(root, words) or None

    async def changes(self, repository: str, branch: str) -> ChangesView:
        """The diff of the branch tip against its fork point, 400 lines at most."""
        facts = await self.facts(repository)
        empty = ChangesView(files=[], cut=False, branch=branch, default_branch=facts.default_branch)
        tip = facts.tips.get(branch) or facts.tips.get(f"origin/{branch}")
        if branch == "" or tip is None or tip == "":
            return empty
        base = await self.fork_point(repository, tip)
        if base is None:
            return empty
        root = await self._root(repository)
        done = await self._runner.run(
            root, ["diff", "--no-color", "--no-renames", base, tip], cap=DIFF_CAP
        )
        if not done.ok and not done.truncated:
            return empty
        parsed = parse_diff(done.stdout, DIFF_LIMIT)
        return ChangesView(
            files=parsed.files, cut=parsed.cut or done.truncated, branch=branch,
            default_branch=facts.default_branch,
        )  # fmt: skip

    async def holds_code(self, repository: str, base: str, tip: str) -> bool:
        """Whether `tip` has a non-merge commit `base` lacks."""
        root = await self._root(repository)
        out = await self._runner.ok(
            root, ["log", "--no-merges", "-1", "--format=%H", f"{base}..{tip}"]
        )
        return bool(out)

    async def changed_paths(self, repository: str, base: str, tip: str) -> list[str]:
        """The paths that differ between two commits."""
        root = await self._root(repository)
        args = [
            "-c",
            "core.quotePath=false",
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            base,
            tip,
        ]
        out = await self._runner.run(root, args)
        return [path for path in out.stdout.split("\0") if path] if out.ok else []

    async def clash(
        self,
        repository: str,
        branch: str,  # noqa: ARG002  # part of the call the follower makes
        tip: str,
        globs: list[str],
    ) -> str | None:
        """Why a branch and main are checked together: a glob both sides changed since the fork."""
        base = await self.fork_point(repository, tip)
        main = fact_rules.base_tip(await self.facts(repository))
        if base is None or main is None:
            return None
        ours = await self.changed_paths(repository, base, tip)
        theirs = await self.changed_paths(repository, base, main)
        return merge_rules.clash(ours, theirs, globs)

    async def tree_name(self, tree_path: Path) -> str:
        """Name the tree by its commit, status and changes; a board tree is validated first."""
        tree_path, clone = await self._guard_path(tree_path)
        run = self._runner

        async def read(args: list[str]) -> str:
            return await run.ok(tree_path, args, clone=clone) or ""

        commit = await read(["rev-parse", "--verify", "HEAD"])
        status = await read(["status", "--porcelain", "-uall"])
        changes = await read(["diff-index", "-p", "HEAD"])
        return digests.tree_name(commit, status, changes)

    async def tree_id(self, repository: str, commit: str) -> str:
        """The id of the tree of `commit`; empty for no commit."""
        if not commit:
            return ""
        root = await self._root(repository)
        named = f"{commit}^{{tree}}"
        return (
            await self._runner.ok(root, ["rev-parse", "--verify", "--end-of-options", named]) or ""
        )

    async def merges(self, repository: str, since: float) -> list[Merge]:
        """The pull requests merged into the default branch at or after `since`."""
        root = await self._root(repository)
        default = (await self.facts(repository)).default_branch
        out = await self._runner.checked(
            root,
            _over(["log", "--format=%H%x09%P%x09%ct%x09%s"], [default]),
            timeout_s=LOG_TIMEOUT_S,
        )
        return merge_rules.parse_merges(out, since)

    async def merge_log(self, repository: str, since: datetime) -> list[LogEntry]:
        """Commits of the default branch since `since`, with whole messages (cap 32 MiB)."""
        root = await self._root(repository)
        default = (await self.facts(repository)).default_branch
        command = ["log", "--format=%H%x1f%P%x1f%ct%x1f%B%x1e", f"--since={since.isoformat()}"]
        done = await self._runner.run(
            root, _over(command, [default]), timeout_s=LOG_TIMEOUT_S, cap=32 * 1024 * 1024
        )
        if not done.ok:
            msg = f"git could not read the log of {repository}"
            raise UnavailableError(msg)
        return merge_rules.parse_log_entries(done.stdout)

    async def merge_conflicts(self, repository: str, tip: str, other: str) -> MergeCheck | None:
        """Whether two commits merge: a stored answer, else `merge-tree`; failures store nothing."""
        pair = tuple(sorted((tip, other)))
        async with self._uow() as session:
            stored = await GitStore(session).merge_check(repository, pair[0], pair[1])
        if stored is not None:
            return stored
        root = await self._root(repository)
        args = ["merge-tree", "--write-tree", "--name-only", "--no-messages", tip, other]
        done = await self._runner.run(root, args)
        files = merge_rules.read_merge_tree(done.code, done.stdout)
        if files is None:
            return None
        check = MergeCheck(clean=not files, files=files)
        async with self._uow() as session:
            await GitStore(session).store_merge_check(
                repository, (pair[0], pair[1]), check, self._clock()
            )
        return check

    async def forget_merge_checks(self, older_than: datetime) -> int:
        """Delete stored merge answers older than `older_than`."""
        async with self._uow() as session:
            return await GitStore(session).forget_merge_checks(older_than)
