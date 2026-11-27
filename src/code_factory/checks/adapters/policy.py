"""What the repository's configuration decides for a contained run."""

from collections.abc import Sequence
from pathlib import Path

from code_factory.git.service import GitService
from code_factory.platform.errors import BadRequestError
from code_factory.platform.programs import NVMRC_BYTES
from code_factory.repositories.service import RepositoryService
from code_factory.settings.service import SettingsService


class CheckPolicy:
    """`ContainedPolicy` over the repository's `[agents] sandbox`, `.nvmrc` and tracked folders."""

    def __init__(
        self,
        settings: SettingsService,
        repositories: RepositoryService,
        git: GitService,
        state_dir: Path,
    ) -> None:
        self._settings = settings
        self._repositories = repositories
        self._git = git
        self._state = state_dir
        self._roots: tuple[Path, ...] = ()

    async def refresh(self) -> None:
        """Read the tracked folders: a program is never taken from where a run may write."""
        self._roots = tuple(Path(record.path) for record in await self._repositories.list())

    async def sandboxed(self, repository: str) -> bool:
        """Whether `[agents] sandbox` is on (it is unless the repository sets it false)."""
        config = await self._settings.load(await self._repositories.get(repository))
        return config.agents is None or config.agents.sandbox is not False

    async def nvmrc(self, repository: str) -> str | None:
        """The main checkout's `.nvmrc`, or None when it is missing or not a plain file."""
        root = await self._repositories.get(repository)
        try:
            return await self._git.read_text_below(root, ".nvmrc", NVMRC_BYTES + 1)
        except BadRequestError:
            return None

    def places(self) -> Sequence[Path]:
        """The folders a run may write: tracked repositories, the state folder."""
        return (*self._roots, self._state)
