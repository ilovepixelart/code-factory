"""Moving commits between a clone and the main repository, saving work, and pushing."""

import contextlib
import shutil
import tempfile
from pathlib import Path

from code_factory.git.adapters import transport
from code_factory.git.adapters.folders import threaded
from code_factory.git.models import (
    FETCH_NOT_FORWARD,
    CatchUp,
    Conflicted,
    Current,
    FetchRefusedError,
    Refused,
    Saved,
    TreeFolders,
    Updated,
    Updating,
)
from code_factory.git.rules import facts as fact_rules
from code_factory.git.rules.branches import LEFT_OUT, branch_refusal, is_plain_segment, wip_ref
from code_factory.git.rules.folders import fast_forward_merge
from code_factory.git.service.trees import TreesMixin
from code_factory.platform.errors import BadRequestError, CodeFactoryError, ConflictError

BRANCH_REDIRECTED = "its branch's ref names another ref, so the board neither moves nor pushes it"
FILTER_SET = "a filter is set in this tree's git config"


class MovesMixin(TreesMixin):
    """Fetch back, save, push, catch up."""

    async def _plain_tip(self, root: Path, branch: str) -> str | None:
        """The id `refs/heads/<branch>` holds when it is a plain ref; `None` when absent."""
        named = f"refs/heads/{branch}"
        out = await self._runner.ok(
            root, ["for-each-ref", "--format=%(refname) %(symref) %(objectname)", named]
        )
        for line in (out or "").splitlines():
            parts = line.split(" ")
            if len(parts) == 3 and parts[0] == named and not parts[1]:  # noqa: PLR2004
                return parts[2]
        if await self._runner.ok(root, ["rev-parse", "--verify", "--quiet", named]) is not None:
            raise FetchRefusedError(BRANCH_REDIRECTED)
        return None

    async def fetch_back(self, repository: str, tree: str, branch: str) -> None:
        """Bring the clone's branch into the main repository as one checked commit, forward only."""
        folders = await self._folders(repository, tree)
        if not folders.is_clone or not branch:
            return
        root = await self._root(repository)
        named, source = f"refs/heads/{branch}", folders.worktree
        commit = await transport.clone_tip(self._runner, root, source, named)
        held = await self._plain_tip(root, branch)
        if held == commit:
            return
        await transport.take_commit(self._runner, root, source, commit)
        if held is not None and not await self.is_ancestor(repository, held, commit):
            raise FetchRefusedError(FETCH_NOT_FORWARD)
        await transport.fetch_into(self._runner, root, source, f"{commit}:{named}")
        self.invalidate(repository)

    async def take_clone_commit(self, repository: str, tree: str, ref: str) -> str:
        """The commit the clone holds for `ref`, taken into the main repository without a ref."""
        folders = await self._folders(repository, tree)
        root = await self._root(repository)
        commit = await transport.clone_tip(self._runner, root, folders.worktree, ref)
        await transport.take_commit(self._runner, root, folders.worktree, commit)
        return commit

    async def _screen(self, repository: str, branch: str, new: str) -> None:
        base = await self.fork_point(repository, new) or ""
        reason = await self._ports.screen.held(repository, branch, base, new)
        if reason is not None:
            msg = f"the screen held the push: {reason}"
            raise ConflictError(msg)

    async def push_commit(self, repository: str, commit: str, branch: str) -> None:
        """The one push every module uses: screened, never forced, never the default branch."""
        why = branch_refusal(branch)
        if why is not None:
            msg = f"bad branch {branch}: {why}"
            raise BadRequestError(msg)
        if (await self.facts(repository)).default_branch == branch:
            msg = f"{branch} is the default branch, which the board never pushes to"
            raise ConflictError(msg)
        await self._screen(repository, branch, commit)
        await transport.push_commit(self._runner, await self._root(repository), commit, branch)

    async def _snapshot(self, path: Path, folders: TreeFolders, ticket_id: str) -> str:
        run, clone = self._runner, folders.is_clone
        config = await run.ok(
            path, ["config", "--show-scope", "--get-regexp", r"^filter\."], clone=clone
        )
        if any(
            not line.startswith(("global\t", "system\t")) for line in (config or "").splitlines()
        ):
            raise BadRequestError(FILTER_SET)
        head = await run.ok(path, ["rev-parse", "--verify", "HEAD"], clone=clone)
        if head is None:
            msg = f"{path} has no commit"
            raise BadRequestError(msg)
        scratch = await threaded(tempfile.mkdtemp)
        try:
            env = {"GIT_INDEX_FILE": f"{scratch}/index"}
            await run.checked(path, ["read-tree", "HEAD"], clone=clone, env=env)
            await run.checked(path, ["add", "-A", "--", ".", *LEFT_OUT], clone=clone, env=env)
            tree = await run.checked(path, ["write-tree"], clone=clone, env=env)
        finally:
            await threaded(lambda: shutil.rmtree(scratch, ignore_errors=True))
        return await self._commit_tree(path, clone, ticket_id, head, tree)

    async def _commit_tree(
        self, path: Path, clone: bool, ticket_id: str, head: str, tree: str
    ) -> str:
        run, name = self._runner, wip_ref(ticket_id)
        previous = await run.ok(path, ["rev-parse", "--verify", "--quiet", name], clone=clone)

        async def tree_of(commit: str) -> str | None:
            return await run.ok(path, ["rev-parse", f"{commit}^{{tree}}"], clone=clone)

        if previous is not None and await tree_of(previous) == tree:
            return previous
        if previous is None and await tree_of(head) == tree:
            commit = head
        else:
            parents = ["-p", head, *(["-p", previous] if previous is not None else [])]
            message = f"{ticket_id}: Save unfinished work"
            commit = await run.checked(
                path, ["commit-tree", tree, *parents, "-m", message], clone=clone
            )
        await run.checked(path, ["update-ref", name, commit], clone=clone)
        return commit

    async def save_work(self, repository: str, ticket_id: str, *, tree: str | None = None) -> Saved:
        """Keep the tree's work in `refs/wip/<id>` (files and index untouched), then push it."""
        if not is_plain_segment(ticket_id):
            msg = f"{ticket_id} is not a ticket id"
            raise BadRequestError(msg)
        folders = await self._folders(repository, tree or ticket_id)
        path = Path(folders.worktree)
        commit = await self._snapshot(path, folders, ticket_id)
        try:
            sent = await self._send(repository, ticket_id, tree or ticket_id, folders, commit)
        except CodeFactoryError as error:
            return Saved(commit=commit, not_sent=str(error))
        return Saved(commit=commit, sent=sent)

    async def _send(
        self, repository: str, ticket_id: str, tree: str, folders: TreeFolders, commit: str
    ) -> list[str]:
        root, run, name = await self._root(repository), self._runner, wip_ref(ticket_id)
        target = f"{commit}:{name}"
        if not folders.is_clone:
            await self._screen(repository, name, commit)
            await self._push_ref(Path(folders.worktree), target)
            return [name]
        recorded = (await self._ports.tickets.ticket(repository, ticket_id)).branch
        branch = (
            recorded if recorded and await self._pushable(repository, folders, recorded) else ""
        )
        await transport.fetch_into(run, root, folders.worktree, target)
        tip = None
        if branch:
            await self.fetch_back(repository, tree, branch)
            tip = await self._plain_tip(root, branch)
        await self._screen(repository, name, commit)
        if tip is not None:
            await self._screen(repository, branch, tip)
        await self._push_ref(root, target)
        sent = [name]
        if tip is not None:
            await transport.push_commit(run, root, tip, branch)
            sent.append(f"refs/heads/{branch}")
        return sent

    async def _pushable(self, repository: str, folders: TreeFolders, branch: str) -> bool:
        """Whether a save may push the branch: not the default, and the clone is on it."""
        try:
            await self._on_ticket_branch(repository, folders, branch)
        except ConflictError:
            return False
        return True

    async def _on_ticket_branch(self, repository: str, folders: TreeFolders, branch: str) -> None:
        if (await self.facts(repository)).default_branch == branch:
            msg = f"{branch} is the default branch, which a save never pushes"
            raise ConflictError(msg)
        on = await self._runner.ok(
            Path(folders.worktree), ["symbolic-ref", "HEAD"], clone=folders.is_clone
        )
        if on != f"refs/heads/{branch}":
            msg = f"the clone is not on the ticket's branch {branch}"
            raise ConflictError(msg)

    async def _push_ref(self, at: Path, target: str) -> None:
        done = await self._runner.run(at, ["push", "--quiet", "origin", target], timeout_s=300.0)
        if not done.ok:
            lines = done.stderr.strip().splitlines()
            msg = f"the push failed: {lines[-1] if lines else 'git said nothing'}"
            raise ConflictError(msg)

    async def catch_up_main(self, repository: str) -> CatchUp:
        """`fetch origin`, then fast-forward the main checkout when it is on the default branch."""
        root = await self._root(repository)
        default = (await self.facts(repository)).default_branch
        try:
            await transport.fetch_origin(self._runner, root)
        except CodeFactoryError as error:
            return CatchUp(moved=False, reason=str(error))
        branch = await self._runner.ok(root, ["branch", "--show-current"]) or ""
        if branch != default:
            self.invalidate(repository)
            return CatchUp(moved=False, reason=f"it is on {branch or 'no branch'}, not {default}")
        async with self._runner.ref_lock(root):
            done = await self._runner.run(root, fast_forward_merge(f"origin/{default}"))
        self.invalidate(repository)
        if done.ok:
            return CatchUp(moved=True)
        words = (done.stderr + "\n" + done.stdout).strip().splitlines()
        return CatchUp(moved=False, reason=words[0] if words else "git said nothing")

    async def update_branch(self, repository: str, ticket_id: str) -> Updating:
        """Merge origin's default tip into the ticket's branch, by plumbing."""
        root = await self._root(repository)
        facts = await self.facts(repository)
        branch = (await self._ports.tickets.ticket(repository, ticket_id)).branch
        tip = await self._plain_tip(root, branch) if branch else None
        main = fact_rules.base_tip(facts)
        if tip is None or main is None:
            return Refused(why=f"{ticket_id} has no branch here to update")
        if await self.is_ancestor(repository, main, tip):
            return Current()
        args = ["merge-tree", "--write-tree", "--name-only", "--no-messages", tip, main]
        done = await self._runner.run(root, args)
        lines = done.stdout.splitlines()
        if done.code == 1 and len(lines) > 1:
            return Conflicted(files=[line for line in lines[1:] if line])
        if not done.ok or not lines:
            return Refused(why="git could not merge the default branch into the branch")
        message = f"Merge {main} into {branch}"
        new = await self._runner.checked(
            root, ["commit-tree", lines[0], "-p", tip, "-p", main, "-m", message]
        )
        try:
            await self.push_commit(repository, new, branch)
        except CodeFactoryError as error:
            return Refused(why=str(error))
        with contextlib.suppress(
            FetchRefusedError
        ):  # checked out in a worktree: only origin took it
            await transport.fetch_into(self._runner, root, str(root), f"{new}:refs/heads/{branch}")
        self.invalidate(repository)
        return Updated(tip=new)
