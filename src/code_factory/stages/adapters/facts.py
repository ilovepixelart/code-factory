"""A repository's tickets' branch facts, from what the git module read of the repository."""

import logging
from collections.abc import Mapping
from typing import Protocol

from code_factory.git.models import GitFacts, TreeInfo
from code_factory.stages.models import BranchFacts
from code_factory.stages.rules import branch_facts

logger = logging.getLogger(__name__)


class GitReads(Protocol):
    """The two reads of `GitService` the facts need."""

    async def facts(self, repository: str) -> GitFacts:
        """The branches, tips, merges and log of the repository."""
        ...

    async def list_trees(self, repository: str) -> list[TreeInfo]:
        """The board-made trees of the repository."""
        ...


class GitServiceFacts:
    """Answers each ticket's facts through `GitService.facts` and the board's trees."""

    def __init__(self, git: GitReads) -> None:
        self._git = git

    async def _worktrees(self, repository: str) -> frozenset[str]:
        """The branches a valid board tree works on; none when the trees cannot be listed."""
        try:
            trees: list[TreeInfo] = await self._git.list_trees(repository)
        except Exception:
            logger.exception("the trees of repository %s cannot be listed", repository)
            return frozenset()
        return frozenset(tree.branch for tree in trees if tree.valid and tree.branch != "")

    async def read(self, repository: str, tickets: Mapping[str, str]) -> dict[str, BranchFacts]:
        """The facts of each ticket (id to its branch) of the repository."""
        git = await self._git.facts(repository)
        worktrees = await self._worktrees(repository)
        return {
            ticket: branch_facts(ticket, branch, git, worktrees=worktrees)
            for ticket, branch in tickets.items()
        }
