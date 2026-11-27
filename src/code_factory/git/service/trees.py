"""The places agents work: recorded clones and linked worktrees."""

import contextlib
import os
import secrets
from pathlib import Path

import anyio

from code_factory.git.adapters import trees as tree_io
from code_factory.git.adapters.folders import exists, snapshot_tree, threaded
from code_factory.git.adapters.transport import fetch_origin
from code_factory.git.models import (
    GitFacts,
    Redirected,
    Removed,
    TreeFolders,
    TreeInfo,
    TreeKind,
    TreeRecord,
    TreeRedirectedError,
)
from code_factory.git.repository import GitStore
from code_factory.git.rules import facts as fact_rules
from code_factory.git.rules.branches import (
    attempt_branch,
    attempt_tree_name,
    branch_for,
    branch_refusal,
)
from code_factory.git.rules.folders import TREES, kept_paths, validate_tree
from code_factory.git.rules.landing import lost_words
from code_factory.git.service.plain import PlainMixin
from code_factory.platform.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnavailableError,
)

LINKED = (
    "{path} is a linked worktree of the main repository, and an agent run starts only in a clone "
    "of its own: once its work is committed, remove it with `code-factory worktrees remove "
    "{ticket}` (its branch stays) and start again"
)


def _info(  # noqa: PLR0913  # the optional columns of a listing row
    record: TreeRecord,
    *,
    ahead: int | None = None,
    uncommitted: int = 0,
    merged: bool = False,
    valid: bool = True,
    orphan: str = "",
) -> TreeInfo:
    return TreeInfo(
        name=record.name,
        kind=record.kind,
        ticket_id=record.ticket_id,
        branch=record.branch,
        path=record.path,
        ahead=ahead,
        uncommitted=uncommitted,
        merged=merged,
        valid=valid,
        orphan=orphan,
    )


class TreesMixin(PlainMixin):
    """Start, validate, list and remove trees."""

    async def validate_tree(self, repository: str, name: str) -> TreeFolders:
        """The folders of a recorded tree; raises `TreeRedirectedError` when they changed."""
        return await self._folders(repository, name)

    async def protected_paths(self, repository: str, name: str) -> list[Path]:
        """What a run's sandbox may not write in this tree."""
        return [Path(p) for p in kept_paths(await self._folders(repository, name))]

    async def start_worktree(
        self, repository: str, ticket_id: str, *, attempt: int = 0, owner_by_hand: bool = False
    ) -> TreeInfo:
        """Make the ticket's tree: a recorded clone for a run, a linked worktree for the owner."""
        root = await self._root(repository)
        name = attempt_tree_name(ticket_id, attempt)
        tree = root / TREES / name
        by_hand = owner_by_hand and attempt == 0
        async with self._runner.tree_lock(tree):
            return await self._start_tree(repository, ticket_id, root, tree, attempt, by_hand)

    async def _start_tree(  # noqa: PLR0913, PLR0917  # identity and kind of one tree
        self, repository: str, ticket_id: str, root: Path, tree: Path, attempt: int, by_hand: bool
    ) -> TreeInfo:
        ticket = await self._ports.tickets.ticket(repository, ticket_id)
        facts = await self.facts(repository)
        if facts.default_branch not in facts.local:
            msg = "the repository has no commits yet, so no branch or worktree can be created"
            raise BadRequestError(msg)
        own = ticket.branch or branch_for(ticket_id)
        why = branch_refusal(own)
        if why is not None:
            msg = f"bad branch {own}: {why}"
            raise BadRequestError(msg)
        name = tree.name
        existing = await self._record(repository, name)
        if existing is not None and existing.kind is TreeKind.WORKTREE and not by_hand:
            raise ConflictError(LINKED.format(path=existing.path, ticket=ticket_id))
        branch = attempt_branch(own, attempt)
        if existing is not None and await threaded(tree.is_dir):
            return _info(existing)
        if existing is not None:  # the row outlived its folder
            async with self._uow() as session:
                await GitStore(session).remove_tree(repository, name)
        if await threaded(lambda: os.path.lexists(tree)):
            msg = f"{tree} exists with no record, so the board neither uses nor deletes it"
            raise ConflictError(msg)
        base = await self._cut_from(repository, ticket_id, own, attempt, facts)
        record = TreeRecord(
            repository=repository, name=name,
            kind=TreeKind.WORKTREE if by_hand else TreeKind.CLONE,
            ticket_id=ticket_id, attempt=attempt, branch=branch, path=str(tree),
            token=secrets.token_hex(16),
        )  # fmt: skip
        await self._make(root, tree, record, base, branch in facts.local)
        if ticket.branch != branch and attempt == 0:
            await self._ports.tickets.record_branch(repository, ticket_id, branch)
        self.invalidate(repository)
        return _info(record).model_copy(update={"made": True})

    async def _cut_from(
        self, repository: str, ticket_id: str, own: str, attempt: int, facts: GitFacts
    ) -> str:
        if attempt > 0:
            return own if own in facts.local else fact_rules.base_branch(facts)
        parent = await self._ports.tickets.stack_parent(repository, ticket_id)
        if parent is not None:
            return fact_rules.stack_base(parent, facts).cut
        return fact_rules.base_branch(facts)

    async def _make(
        self, root: Path, tree: Path, record: TreeRecord, base: str, exists: bool
    ) -> None:
        run = self._runner
        clone = record.kind is TreeKind.CLONE
        owned = False
        try:
            if clone:
                with anyio.CancelScope(shield=True):
                    await tree_io.reserve_clone(root, tree)
                owned = True
            async with run.ref_lock(root):
                await tree_io.exclude_trees_folder(run, root)
                if not clone:
                    owned = True
                    await tree_io.make_worktree(
                        run, root, tree, record.branch, None if exists else base
                    )
                else:
                    if not exists:
                        await run.checked(
                            root, ["branch", "--no-track", "--end-of-options", record.branch, base]
                        )
                    await tree_io.make_clone(run, root, tree, record.branch, record.token)
            if clone:
                await self._set_up(record, root)
            await self._insert(record)
        except BaseException:
            if owned:
                with anyio.CancelScope(shield=True):
                    await self._remove_folder(record.repository, tree)
            raise

    async def _insert(self, record: TreeRecord) -> None:
        async with self._uow() as session:
            added = await GitStore(session).add_tree(record)
        if not added:
            msg = f"{record.name} is already recorded for {record.repository}"
            raise ConflictError(msg)

    async def _set_up(self, record: TreeRecord, root: Path) -> None:
        snapshot = await threaded(lambda: snapshot_tree(Path(record.path), root))
        checked = validate_tree(snapshot, record)
        if isinstance(checked, Redirected):
            raise TreeRedirectedError(checked.reason)
        outcome = await self._ports.hooks.run_setup(record.repository, Path(checked.worktree))
        if outcome.code == 0:
            return
        said = (
            "did not finish in time"
            if outcome.code is None
            else f"failed with exit code {outcome.code}"
        )
        msg = f"the worktree setup {said}" + (f"; see {outcome.log}" if outcome.log else "")
        raise UnavailableError(msg)

    async def _remove_folder(self, repository: str, tree: Path) -> None:
        root = await self._root(repository)
        common = await self._common(repository)
        async with self._runner.ref_lock(root):
            await tree_io.remove_tree(root, common, tree)

    async def remove_tree(self, repository: str, name: str) -> None:
        """Trash then delete the tree's folder, then its row; one outside the folder is refused."""
        record = await self._record(repository, name)
        root = await self._root(repository)
        tree = Path(record.path) if record else root / TREES / name
        if record is None and not tree.exists():
            msg = f"no tree {name} in {repository}"
            raise NotFoundError(msg)
        await self._remove_folder(repository, tree)
        if record is not None and record.kind is TreeKind.WORKTREE:
            await self._runner.run(root, ["worktree", "prune"])
        async with self._uow() as session:
            await GitStore(session).remove_tree(repository, name)
        self.invalidate(repository)

    async def empty_trash(self, repository: str) -> list[tuple[str, str]]:
        """Delete what a stop left; then drop git's entries for worktrees no longer there."""
        left = await tree_io.empty_trash(await self._common(repository))
        await self._runner.run(await self._root(repository), ["worktree", "prune"])
        return left

    async def reconcile_trees(self, repository: str) -> list[str]:
        """Delete rows whose folder is gone; the folders that have no row (never trusted)."""
        try:
            root = await self._root(repository)
        except NotFoundError:
            async with self._uow() as session:
                store = GitStore(session)
                for record in await store.trees(repository):
                    await store.remove_tree(repository, record.name)
            return []
        async with self._uow() as session:
            records = await GitStore(session).trees(repository)
        gone = [r.name for r in records if not await exists(Path(r.path))]
        async with self._uow() as session:
            for name in gone:
                await GitStore(session).remove_tree(repository, name)
        folder = root / TREES
        known = {r.name for r in records}
        present = await threaded(
            lambda: sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []
        )
        return [name for name in present if name not in known and not name.startswith("check-")]

    async def list_trees(self, repository: str) -> list[TreeInfo]:
        """Rows joined with their folders; a row without a folder, or the reverse, is flagged."""
        root = await self._root(repository)
        async with self._uow() as session:
            records = await GitStore(session).trees(repository)
        listed = [await self._described(repository, r) for r in records]
        known = {r.name for r in records}
        folder = root / TREES
        present = await threaded(
            lambda: sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []
        )
        listed += [
            TreeInfo(name=n, kind=TreeKind.CLONE, ticket_id="", branch="", path=str(folder / n),
                     valid=False, orphan="a folder with no record, never trusted")
            for n in present if n not in known and not n.startswith("check-")
        ]  # fmt: skip
        return listed

    async def _described(self, repository: str, record: TreeRecord) -> TreeInfo:
        if not await exists(Path(record.path)):
            return _info(record, valid=False, orphan="the folder is gone")
        try:
            folders = await self._folders(repository, record.name)
        except Exception as error:  # noqa: BLE001  # a redirected tree is listed, not raised
            return _info(record, valid=False, orphan=str(error))
        facts = await self.facts(repository)
        base = fact_rules.base_branch(facts)
        run = self._runner
        path = Path(folders.worktree)
        count = await run.ok(path, ["rev-list", "--count", f"{base}..HEAD"], clone=folders.is_clone)
        status = await run.ok(path, ["status", "--porcelain", "-uall"], clone=folders.is_clone)
        merged = (
            await run.run(
                path, ["merge-base", "--is-ancestor", "HEAD", base], clone=folders.is_clone
            )
        ).ok
        return _info(
            record, ahead=int(count) if count is not None and count.isdigit() else None,
            uncommitted=len([line for line in (status or "").splitlines() if line]), merged=merged,
        )  # fmt: skip

    async def remove_worktree(self, repository: str, ticket_id: str) -> Removed:
        """Remove a hand-made worktree and its branch when nothing would be lost."""
        record = await self._record(repository, ticket_id)
        if record is None or record.kind is not TreeKind.WORKTREE:
            msg = (
                f"no worktree {ticket_id}: `code-factory worktrees list` names them, "
                "and a run's clone is none"
            )
            raise NotFoundError(msg)
        folders = await self._folders(repository, ticket_id)
        root = await self._root(repository)
        with contextlib.suppress(UnavailableError):  # a stale ref only says "not merged"
            await fetch_origin(self._runner, root)
        facts = await self.facts(repository)
        base = fact_rules.base_branch(facts)
        path = Path(folders.worktree)
        lost = await self._lost(path, base)
        if lost is not None:
            msg = (
                f"{ticket_id} holds {lost}, which removing it would lose: `code-factory save "
                f"{ticket_id}` copies them to a ref, `code-factory land {ticket_id}` merges them"
            )
            raise ConflictError(msg)
        branch = await self._runner.ok(path, ["branch", "--show-current"]) or ""
        async with self._runner.ref_lock(root):
            await self._runner.checked(root, ["worktree", "remove", str(path)])
            deleted = (
                bool(branch)
                and branch != facts.default_branch
                and (await self._runner.run(root, ["branch", "-q", "-D", "--", branch])).ok
            )
        async with self._uow() as session:
            await GitStore(session).remove_tree(repository, ticket_id)
        self.invalidate(repository)
        return Removed(branch=branch, branch_deleted=deleted)

    async def _lost(self, path: Path, base: str) -> str | None:
        run = self._runner
        status = (
            await run.ok(
                path,
                [
                    "-c",
                    "core.quotePath=false",
                    "status",
                    "--porcelain",
                    "--no-renames",
                    "--untracked-files=all",
                ],
            )
            or ""
        )
        files = [line[3:].strip() for line in status.splitlines() if line.strip()]
        commits: list[str] = []
        merged = (await run.run(path, ["merge-base", "--is-ancestor", "HEAD", base])).ok
        if not merged:
            cherry = await run.ok(path, ["cherry", base, "HEAD"]) or ""
            if any(line.startswith("+") for line in cherry.splitlines()):
                log = await run.ok(path, ["log", "--format=%h %s", f"{base}..HEAD"]) or ""
                commits = [line for line in log.splitlines() if line]
        return lost_words(files, commits)

    async def add_snapshot(self, repository: str, commit: str) -> Path:
        """A detached worktree `check-*` of `commit` under the trees folder (unrecorded)."""
        root = await self._root(repository)
        tree = root / TREES / f"check-{secrets.token_hex(4)}"
        async with self._runner.ref_lock(root):
            await tree_io.exclude_trees_folder(self._runner, root)
        await tree_io.make_snapshot(self._runner, root, tree, commit)
        return tree

    async def remove_snapshot(self, repository: str, path: Path) -> None:
        """Remove a `check-*` snapshot made by `add_snapshot`."""
        root = await self._root(repository)
        if path.parent != root / TREES or not path.name.startswith("check-"):
            msg = f"{path} is not a snapshot made by the board"
            raise BadRequestError(msg)
        await self._remove_folder(repository, path)
        await self._runner.run(root, ["worktree", "prune"])

    async def copy_commit(self, repository: str, commit: str, dest: Path) -> None:
        """A repository of its own at `dest`, holding the main repository's refs, at `commit`."""
        root = await self._root(repository)
        await tree_io.make_clone(self._runner, root, dest, commit, tree_io.new_token())


__all__ = ["Redirected", "TreesMixin", "validate_tree"]
