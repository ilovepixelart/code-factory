"""Landing a branch by hand: merge main in, push, open the pull request, merge when it is clean."""

from dataclasses import dataclass
from pathlib import Path

from code_factory.git.adapters import transport
from code_factory.git.models import (
    Conflicted,
    Landed,
    Merged,
    NotMerged,
    Refused,
    TreeFolders,
    TreeKind,
    TreeRedirectedError,
)
from code_factory.git.rules import facts as fact_rules
from code_factory.git.rules.branches import is_plain_segment
from code_factory.git.rules.landing import choose_landing_head
from code_factory.git.service.moves import MovesMixin
from code_factory.platform.errors import CodeFactoryError


def moved(pinned: str, head: str) -> str:
    """Why a landing pinned to `pinned` stops."""
    return f"the tip moved from {pinned} to {head}"


@dataclass(frozen=True)
class _Job:
    """One land: what the steps share."""

    repository: str
    ticket_id: str
    kind: TreeKind
    folders: TreeFolders
    branch: str
    default: str
    tip: str  # origin's default branch, read once
    pinned: str | None


class _Stop(Exception):  # noqa: N818  # carries the answer out of the steps
    def __init__(self, answer: Landed) -> None:
        super().__init__()
        self.answer = answer


class LandingMixin(MovesMixin):
    """`land`."""

    async def land(self, repository: str, ticket_id: str, *, pinned: str | None = None) -> Landed:
        """Land the ticket's tree: the steps in order, the first refusal ends it with its words."""
        try:
            return await self._land(repository, ticket_id, pinned)
        except _Stop as stop:
            return stop.answer
        except TreeRedirectedError as error:
            return Refused(why=f"{ticket_id} is not a clone or worktree the board made: {error}")
        except CodeFactoryError as error:
            return Refused(why=str(error))

    async def _branch_of(self, repository: str, ticket_id: str, folders: TreeFolders) -> str:
        ticket = await self._ports.tickets.ticket(repository, ticket_id)
        if folders.is_clone:
            branch = ticket.branch
            if not branch:
                raise _Stop(Refused(why=f"{ticket_id} records no branch"))
            await self._on_ticket_branch(repository, folders, branch)
            return branch
        shown = await self._runner.ok(Path(folders.worktree), ["branch", "--show-current"])
        if shown is None or shown == "":
            raise _Stop(Refused(why="its worktree names no branch"))
        return shown

    async def _land(self, repository: str, ticket_id: str, pinned: str | None) -> Landed:
        if not is_plain_segment(ticket_id):
            return Refused(why=f"{ticket_id} is not a ticket id")
        record = await self._record(repository, ticket_id)
        if record is None:
            return Refused(why=f"no tree {ticket_id} for {repository}")
        folders = await self._folders(repository, ticket_id)
        root, path = await self._root(repository), Path(folders.worktree)
        branch = await self._branch_of(repository, ticket_id, folders)
        default = (await self.facts(repository)).default_branch
        if branch == default:
            return Refused(why=f"its worktree is on the default branch {default}")
        await transport.fetch_origin(self._runner, root)
        tip = await self._runner.ok(root, ["rev-parse", "--verify", "-q", f"origin/{default}"])
        if tip is None or tip == "":
            return Refused(why=f"origin/{default} names no commit")
        job = _Job(repository, ticket_id, record.kind, folders, branch, default, tip, pinned)
        head = await self._head(job)
        await self.push_commit(repository, head, branch)
        return await self._finish(job, head, path)

    async def _head(self, job: _Job) -> str:
        folders, pinned = job.folders, job.pinned
        path = Path(folders.worktree)
        if not folders.is_clone:
            if pinned is not None:
                current = await self._runner.ok(path, ["rev-parse", "HEAD"]) or ""
                if current != pinned:
                    raise _Stop(NotMerged(why=moved(pinned, current)))
            if not await self._is_ancestor_in(path, job.tip, "HEAD"):
                await self._merge_in(path, job.tip)
            return await self._runner.checked(path, ["rev-parse", "HEAD"])
        named = f"refs/heads/{job.branch}"
        commit = await self.take_clone_commit(job.repository, job.ticket_id, named)
        if pinned is not None and pinned != commit:
            raise _Stop(NotMerged(why=moved(pinned, commit)))
        await self._screen(job.repository, job.branch, commit)
        await self.fetch_back(job.repository, job.ticket_id, job.branch)
        return await self._clone_head(job.repository, job.branch, commit, job.tip)

    async def _is_ancestor_in(self, path: Path, older: str, newer: str) -> bool:
        return (await self._runner.run(path, ["merge-base", "--is-ancestor", older, newer])).ok

    async def _merge_in(self, tree: Path, tip: str) -> None:
        done = await self._runner.run(tree, ["merge", "-q", "--no-edit", tip])
        if done.ok:
            return
        listed = await self._runner.ok(tree, ["diff", "--name-only", "--diff-filter=U"]) or ""
        await self._runner.run(tree, ["merge", "--abort"])
        if not listed:
            lines = (done.stderr + done.stdout).strip().splitlines()
            raise _Stop(Refused(why=lines[-1] if lines else "git could not merge"))
        raise _Stop(Conflicted(files=listed.splitlines()))

    async def _pushed_is_ours(self, root: Path, pushed: str, commit: str, tip: str) -> bool:
        if not (await self._runner.run(root, ["merge-base", "--is-ancestor", commit, pushed])).ok:
            return False
        added = await self._runner.ok(root, ["rev-list", pushed, f"^{commit}", f"^{tip}"])
        for added_commit in (added or "").splitlines():
            if not await self._merge_of_parents(root, added_commit):
                return False
        return True

    async def _merge_of_parents(self, root: Path, commit: str) -> bool:
        listing = await self._runner.ok(root, ["rev-list", "--parents", "-n", "1", commit]) or ""
        words = listing.split()
        if len(words) != 3:  # noqa: PLR2004  # the commit and its two parents
            return False
        merged = await self._runner.run(root, ["merge-tree", "--write-tree", words[1], words[2]])
        own = await self._runner.ok(root, ["rev-parse", f"{commit}^{{tree}}"])
        return merged.ok and merged.stdout.strip() == own

    async def _clone_head(self, repository: str, branch: str, commit: str, tip: str) -> str:
        root, run = await self._root(repository), self._runner
        pushed = await run.ok(root, ["rev-parse", "--verify", "-q", f"origin/{branch}"])
        ours = bool(pushed) and await self._pushed_is_ours(root, pushed or "", commit, tip)
        choice = choose_landing_head(
            clone_tip=commit,
            clone_holds_main=await self._is_ancestor_in(root, tip, commit),
            pushed=pushed,
            pushed_is_ours=ours,
            first_holds_main=await self._is_ancestor_in(
                root, tip, pushed if ours and pushed else commit
            ),
        )
        if choice.head is not None:
            if choice.head != commit:
                await self._screen(repository, branch, choice.head)
            return choice.head
        args = ["merge-tree", "--write-tree", "--name-only", "--no-messages", choice.first, tip]
        done = await run.run(root, args)
        lines = done.stdout.splitlines()
        if not done.ok:
            files = [line for line in lines[1:] if line]
            raise _Stop(
                Conflicted(files=files) if files else Refused(why="git could not merge main in")
            )
        message = f"Merge {tip} into {branch}"
        head = await run.checked(
            root, ["commit-tree", lines[0], "-p", choice.first, "-p", tip, "-m", message]
        )
        await self._screen(repository, branch, head)
        return head

    async def _finish(self, job: _Job, head: str, path: Path) -> Landed:
        ports, repository, pinned = self._ports, job.repository, job.pinned
        ticket = await ports.tickets.ticket(repository, job.ticket_id)
        pull = await ports.forge.open_pull(
            repository,
            branch=job.branch,
            head=head,
            base=job.default,
            title=f"{job.ticket_id}: {ticket.title}",
        )
        if await ports.checks.configured(repository):
            verdict = await ports.checks.verdict(repository, job.ticket_id, head)
            if verdict == "failed":
                return NotMerged(why=f"the board's checks failed on {head}")
            if verdict != "passed":
                return NotMerged(why=f"waits for the board's checks on {head}")
        await transport.fetch_origin(self._runner, await self._root(repository))
        if pinned is not None and job.kind is TreeKind.WORKTREE:
            current = await self._runner.ok(path, ["rev-parse", "HEAD"]) or ""
            if current != pinned:
                return NotMerged(why=moved(pinned, current))
        try:
            await ports.forge.merge(job.ticket_id, pull, head)
        except CodeFactoryError as error:
            return NotMerged(why=str(error))
        return Merged(url=pull.url + await self._after_merge(repository, job.ticket_id))

    async def _after_merge(self, repository: str, ticket_id: str) -> str:
        notes = ""
        try:
            await self.remove_tree(repository, ticket_id)
        except CodeFactoryError as error:
            notes += f" (its tree is kept: {error})"
        moved_main = await self.catch_up_main(repository)
        if not moved_main.moved:
            notes += f" (the main checkout did not move: {moved_main.reason})"
        return notes


__all__ = ["LandingMixin", "fact_rules"]
