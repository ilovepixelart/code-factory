"""The srt settings of the board's contained work, from the agents kit's sandbox rules.

`SandboxSettings` and `CheckoutDenials` for the checks module: the state folder, in each of its
forms, and the secret files are denied to read; a command writes its tree and its temporary folder
only; only a worktree setup reaches hosts, the repository's `[agents] allowed_domains` or the
package registries.
"""

from pathlib import Path

import anyio

from code_factory.agents.service import AgentService
from code_factory.repositories.service import RepositoryService
from code_factory.settings.service import SettingsService

# What the board reads in a checkout of its own outside any sandbox: its config and its trees.
BOARD_FOLDERS = (".code-factory",)


class KitSandbox:
    """The srt settings of one contained run, made by the agents kit's rules."""

    def __init__(
        self,
        agents: AgentService,
        settings: SettingsService,
        repositories: RepositoryService,
        state_dir: Path,
    ) -> None:
        self._kit = agents.kit
        self._settings = settings
        self._repositories = repositories
        self._home = str(state_dir)
        self._state = self._kit.state_forms(self._home, str(state_dir.resolve()))

    async def tree_settings(
        self, repository: str, tree: Path, log: Path, temporary: Path, *, reaches_hosts: bool
    ) -> str:
        """A check or a worktree hook in `tree`; only a setup (`reaches_hosts`) reaches hosts."""
        return self._kit.tree_settings(
            state=self._state, home=self._home, tree=str(tree), log=str(log),
            scratch=str(temporary), keys=[],
            hosts=await self._hosts(repository) if reaches_hosts else [],
            denied=await self._denied(repository, tree),
        )  # fmt: skip

    async def git_settings(self, repository: str, tree: Path, log: Path, temporary: Path) -> str:
        """The board's git in `tree`, which may not write the tree's `.git`."""
        del repository  # the rules are the same for every repository
        return self._kit.git_settings(
            state=self._state, home=self._home, tree=str(tree), log=str(log),
            scratch=str(temporary), keys=[], denied=[str(tree / ".git")],
        )  # fmt: skip

    async def preview_settings(
        self, repository: str, tree: Path, log: Path, temporary: Path
    ) -> str:
        """A live preview of `tree`."""
        return self._kit.preview_settings(
            state=self._state, home=self._home, tree=str(tree), log=str(log),
            scratch=str(temporary), keys=[], denied=await self._denied(repository, tree),
        )  # fmt: skip

    async def checkout_denials(self, repository: str, tree: Path) -> list[Path]:
        """What the board reads in `tree`, a checkout of its own, outside any sandbox."""
        del repository  # the board's folders have the same names in every repository
        found = self._kit.checkout_denials(str(tree), BOARD_FOLDERS, is_checkout=True, clones=None)
        return [Path(path) for path in found]

    async def _denied(self, repository: str, tree: Path) -> list[str]:
        """The checkout denials of a tree with a git folder of its own; nothing for a worktree."""
        if not await anyio.Path(tree / ".git").is_dir():
            return []
        return [str(path) for path in await self.checkout_denials(repository, tree)]

    async def _hosts(self, repository: str) -> list[str]:
        config = await self._settings.load(await self._repositories.get(repository))
        configured = None if config.agents is None else config.agents.allowed_domains
        return self._kit.allowed_domains(configured)
