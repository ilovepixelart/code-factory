"""Small reads other modules ask of git: one command each, always through the runner."""

import tempfile
from pathlib import Path

from code_factory.git.adapters.folders import common_dir_of, read_text_below, threaded
from code_factory.git.adapters.runner import NETWORK_TIMEOUT_S
from code_factory.git.models import LogEntry
from code_factory.git.rules import facts as fact_rules
from code_factory.git.rules import merges as merge_rules
from code_factory.git.service.reads import ReadsMixin
from code_factory.platform.errors import BadRequestError, NotFoundError, UnavailableError

PROBE_MINIMUM = "git 2.38 or later (merge-tree --write-tree)"


class PlainMixin(ReadsMixin):
    """Single-command reads."""

    async def is_ancestor(self, repository: str, older: str, newer: str) -> bool:
        """Whether `older` is an ancestor of (or the same as) `newer`."""
        root = await self._root(repository)
        words = ["merge-base", "--is-ancestor", "--end-of-options", older, newer]
        return (await self._runner.run(root, words)).ok

    async def has_commit(self, repository: str, commit: str) -> bool:
        """Whether the repository holds `commit` as a commit."""
        root = await self._root(repository)
        found = await self._runner.ok(root, ["cat-file", "-t", f"{commit}^{{commit}}"])
        return found == "commit"

    async def head_of(self, path: Path) -> str:
        """The commit checked out at `path` (a board tree is validated first); empty with none."""
        path, clone = await self._guard_path(path)
        return await self._runner.ok(path, ["rev-parse", "--verify", "HEAD"], clone=clone) or ""

    async def head_commit(self, repository: str) -> str:
        """The commit checked out in the main checkout; empty on an unborn branch."""
        return (
            await self._runner.ok(await self._root(repository), ["rev-parse", "--verify", "HEAD"])
            or ""
        )

    async def base_tip(self, repository: str) -> str | None:
        """The tip work forks from: origin's default branch when tracked, else the local one."""
        return fact_rules.base_tip(await self.facts(repository))

    async def origin_main_tip(self, repository: str) -> str | None:
        """`origin/<default>` as last fetched, by id."""
        facts = await self.facts(repository)
        return facts.tips.get(f"origin/{facts.default_branch}") or None

    async def remote_tip(self, repository: str, branch: str) -> str | None:
        """What origin itself holds for `branch` (one `ls-remote`), not the stale local ref."""
        root = await self._root(repository)
        done = await self._runner.run(
            root, ["ls-remote", "origin", f"refs/heads/{branch}"], timeout_s=NETWORK_TIMEOUT_S
        )
        for line in done.stdout.splitlines() if done.ok else []:
            commit, _, name = line.partition("\t")
            if name == f"refs/heads/{branch}":
                return commit
        return None

    async def remote_url(self, repository: str) -> str | None:
        """The URL of `origin`."""
        root = await self._root(repository)
        return await self._runner.ok(root, ["remote", "get-url", "origin"]) or None

    async def tracked_files(self, repository: str, patterns: list[str] | None = None) -> list[str]:
        """The files of the main checkout's `HEAD`, optionally limited by pathspecs."""
        root = await self._root(repository)
        args = [
            "ls-files",
            "-z",
            *(["--", *patterns] if patterns is not None and len(patterns) > 0 else []),
        ]
        done = await self._runner.run(root, ["-c", "core.quotePath=false", *args])
        return [name for name in done.stdout.split("\0") if name] if done.ok else []

    async def read_file_at(self, repository: str, commit: str, path: str) -> str | None:
        """The text of `path` as `commit` holds it; `None` when it does not."""
        root = await self._root(repository)
        done = await self._runner.run(root, ["show", f"{commit}:{path}"])
        return done.stdout if done.ok else None

    async def subject(self, repository: str, commit: str) -> str | None:
        """The subject line of `commit`."""
        root = await self._root(repository)
        return await self._runner.ok(
            root, ["log", "-1", "--format=%s", "--end-of-options", commit, "--"]
        )

    @staticmethod
    def merged_branch(subject: str) -> str | None:
        """The branch a merge commit's subject says it merged."""
        return fact_rules.merged_branch(subject)

    @staticmethod
    def branch_refusal(name: str) -> str | None:
        """Why `name` is not a plain branch name."""
        from code_factory.git.rules.branches import branch_refusal  # noqa: PLC0415

        return branch_refusal(name)

    async def first_parent_merges(self, repository: str, since: float, until: float) -> list[str]:
        """Merge commits on the default branch's first-parent line with `since <= time < until`."""
        return [m.commit for m in await self.merges(repository, since) if m.at < until]

    async def read_new_commits(self, repository: str, base: str, new: str) -> list[LogEntry]:
        """The commits `new` adds to `base`, oldest first, with whole messages."""
        root = await self._root(repository)
        args = [
            "log",
            "--reverse",
            "--format=%H%x1f%P%x1f%ct%x1f%B%x1e",
            "--end-of-options",
            f"{base}..{new}",
            "--",
        ]
        done = await self._runner.run(root, args)
        if not done.ok:
            msg = f"git could not read the commits {base}..{new}"
            raise UnavailableError(msg)
        return merge_rules.parse_log_entries(done.stdout)

    async def branch_cut(self, repository: str, branch: str) -> float | None:
        """When a branch was cut: its oldest reflog time, else its oldest commit past the base."""
        root = await self._root(repository)
        reflog = await self._runner.ok(
            root,
            ["reflog", "show", "--format=%ct", "--end-of-options", f"refs/heads/{branch}", "--"],
        )
        times = [t for t in (reflog or "").splitlines() if t.isdigit()]
        if not times:
            base = fact_rules.base_branch(await self.facts(repository))
            log = await self._runner.ok(
                root, ["log", "--format=%ct", "--end-of-options", f"{base}..{branch}", "--"]
            )
            times = [t for t in (log or "").splitlines() if t.isdigit()]
        return float(min(times, key=int)) if times else None

    async def main_checkout(self, path: Path) -> Path:
        """The main checkout of the repository `path` is in, a linked worktree resolved to it."""
        top = await self._runner.ok(path, ["rev-parse", "--show-toplevel"])
        if top is None:
            msg = f"{path} is not in a git repository: git init it first"
            raise NotFoundError(msg)
        common = await threaded(lambda: common_dir_of(Path(top)))
        return common.parent if common is not None and common.name == ".git" else Path(top)

    async def read_text_below(self, root: Path, relative: str, limit: int) -> str | None:
        """A file below `root` read without following links; see `adapters.folders`."""
        if limit < 1:
            msg = "the limit must be at least 1 byte"
            raise BadRequestError(msg)
        return await read_text_below(root, relative, limit)

    async def probe(self) -> None:
        """Fail with a sentence when this git cannot run `merge-tree --write-tree`."""
        with tempfile.TemporaryDirectory() as scratch:
            folder = Path(scratch)
            await self._runner.checked(folder, ["init", "--quiet", "."])
            commit = ["-c", "user.name=probe", "-c", "user.email=probe@localhost", "commit"]
            await self._runner.checked(folder, [*commit, "--quiet", "--allow-empty", "-m", "probe"])
            done = await self._runner.run(folder, ["merge-tree", "--write-tree", "HEAD", "HEAD"])
        if done.code is None or done.code > 1 or "unknown option" in done.stderr:
            msg = f"this git cannot run the board's merge checks; install {PROBE_MINIMUM}"
            raise UnavailableError(msg)
