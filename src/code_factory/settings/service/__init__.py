"""The settings module's public API: the typed view of a repository's `.code-factory/` folder.

No call holds a database transaction across a file or git call: a session per call, committed
before the next file read.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import anyio

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError
from code_factory.settings.adapters import (
    ConfigCache,
    Files,
    FileTimedOut,
    GitFacts,
    in_thread,
)
from code_factory.settings.adapters.scanning import home_folder
from code_factory.settings.models.config import RepositoryConfig
from code_factory.settings.models.errors import ConfigUnjudgedError, unjudged_message
from code_factory.settings.models.kinds import TICKET_TYPES
from code_factory.settings.models.predicates import INTAKE_KEY_PREFIX, key_name, tracker_allowed
from code_factory.settings.models.problems import (
    BoardSettings,
    ConfigReport,
    ExceptionsReport,
    IntakeGrant,
    ReviewGuide,
    TicketFacts,
)
from code_factory.settings.repository import BoardSettingsRepository, GrantRepository
from code_factory.settings.rules import (
    ticket_prefix,
)
from code_factory.settings.rules.config import loaded_config, names_container_mounts
from code_factory.settings.rules.secrets import VALIDATION_HOME, Unjudged
from code_factory.settings.rules.templates import (
    AGENTS_FOLDER,
    CONFIG_BYTES,
    DOCUMENT_TEMPLATES,
    TEMPLATE_BYTES,
    TEMPLATES_FOLDER,
    is_stage,
    ticket_template_path,
)
from code_factory.settings.service.checks import ConfigChecks, resolver_for
from code_factory.settings.service.paths import (
    CONFIG_FILE,
    EXCEPTIONS_FILE,
    REVIEW_GUIDE_FILE,
    TIMED_OUT,
)
from code_factory.settings.tables import BOARD_SETTING_KEYS


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


class SettingsService:
    """Reads and checks the configuration of tracked repositories, and holds tracker key grants."""

    def __init__(
        self,
        uow: UnitOfWork,
        *,
        clock: Callable[[], datetime] = _utcnow,
        files: Files | None = None,
        git: GitFacts | None = None,
        home: Path | None = None,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._files = files or Files()
        self._git = git or GitFacts()
        self._homes = (VALIDATION_HOME, home_folder(home))
        self._cache = ConfigCache()
        self._tickets: TicketFacts | None = None
        self._checks = ConfigChecks(uow, clock, self._files, self._git, self._homes)

    def bind_ticket_facts(self, facts: TicketFacts) -> None:
        """Let `check_exceptions` ask whether the tickets its entries name exist.

        The tickets module's `provide` calls this; this module imports no other module.
        """
        self._tickets = facts
        self._checks.bind_ticket_facts(facts)

    async def load(self, root: Path) -> RepositoryConfig:
        """The lenient typed config of the repository at `root`.

        A missing, unreadable or non-table file is an empty config, each invalid key is dropped and
        the rest read. One `stat` per call: the parse is cached by the file's modification time,
        size and inode, for at most 64 roots. The returned object is shared: do not change it.

        Raises `ConfigUnjudgedError` when a read or the scan ran out of time before it judged the
        mounts: a file that cannot be read in time may hold some.
        """
        try:
            key = await self._files.stat(root, CONFIG_FILE, strict=True)
            if key is None:
                self._cache.drop(root)
                return RepositoryConfig()
            if (cached := self._cache.get(root, key)) is not None:
                return cached
            text = await self._files.read_below(root, CONFIG_FILE, CONFIG_BYTES, strict=True)
        except FileTimedOut as timed_out:
            raise self._refusal(root, ()) from timed_out
        if text is None:
            self._cache.drop(root)
            return RepositoryConfig()
        try:
            parsed = await in_thread(
                loaded_config, text, self._homes, resolver_for(self._homes, root)
            )
        except Unjudged as scan:
            raise self._refusal(root, scan.entries) from scan
        if parsed is None:
            # A timed-out parse is not remembered as an empty config.
            if await in_thread(names_container_mounts, text) is not False:
                raise self._refusal(root, ())
            self._cache.drop(root)
            return RepositoryConfig()
        config, mounted = parsed
        if mounted:
            # Where a mount leads is on disk, not in the file: judged afresh on every load.
            self._cache.drop(root)
            return config
        self._cache.put(root, key, config)
        return config

    def _refusal(self, root: Path, entries: tuple[str, ...]) -> ConfigUnjudgedError:
        self._cache.drop(root)
        return ConfigUnjudgedError(f"{CONFIG_FILE}: {unjudged_message(entries)}")

    async def repository_root(self, path: Path) -> Path:
        """The root of the repository holding `path`; `path` itself outside one."""
        resolved = Path(await anyio.Path(path).resolve())
        return await self._git.toplevel(resolved) or resolved

    async def main_checkout(self, path: Path) -> Path:
        """The main checkout of the repository holding `path`, where its configuration is read.

        `path` itself when it is in no repository.
        """
        resolved = Path(await anyio.Path(path).resolve())
        return await self._git.main_checkout(resolved) or resolved

    async def checkout_of(self, path: Path) -> Path | None:
        """The main checkout of the repository holding `path`, None when it is in none."""
        return await self._git.main_checkout(Path(await anyio.Path(path).resolve()))

    async def ticket_prefix(self, root: Path) -> str:
        """`tickets.prefix` when valid, else `CF`."""
        return ticket_prefix(await self.load(root))

    async def documents_for(self, root: Path, ticket_type: str) -> tuple[str, ...] | None:
        """The `[documents]` entry of a type in canonical order, None when unset or malformed.

        The caller applies its default rule, so a malformed entry never loosens a gate.
        """
        if ticket_type not in TICKET_TYPES:
            raise BadRequestError(f"unknown type {ticket_type}")
        documents = (await self.load(root)).documents
        entry = None if documents is None else getattr(documents, ticket_type, None)
        return tuple(str(item) for item in entry) if isinstance(entry, list) else None

    async def ticket_template(self, root: Path, ticket_type: str) -> str:
        """The text of the repository's template for a ticket type, `""` when there is none."""
        path = ticket_template_path(ticket_type)
        if path is None:
            raise BadRequestError(f"unknown type {ticket_type}")
        return await self._files.read_below(root, path, TEMPLATE_BYTES) or ""

    async def document_template(
        self, root: Path, name: Literal["requirements", "spec", "uat", "mock"]
    ) -> str:
        """The text of the repository's template of a ticket document, `""` when there is none."""
        if name not in DOCUMENT_TEMPLATES:
            raise BadRequestError(f"unknown document {name}")
        return (
            await self._files.read_below(root, f"{TEMPLATES_FOLDER}/{name}.md", TEMPLATE_BYTES)
            or ""
        )

    async def agent_instructions(self, root: Path, stage: str) -> str:
        """The repository's own instructions for a stage, stripped, `""` when it has none."""
        if not is_stage(stage):
            msg = f"unknown stage {stage!r}: a stage is lowercase letters, digits and -"
            raise BadRequestError(msg)
        text = await self._files.read_below(root, f"{AGENTS_FOLDER}/{stage}.md", TEMPLATE_BYTES)
        return (text or "").strip()

    async def automation_template(self, root: Path, path: str) -> str | None:
        """An automation's template: a file below the repository, no link followed; else None."""
        return await self._files.read_below(root, path, TEMPLATE_BYTES)

    async def review_guide(self, root: Path) -> ReviewGuide | None:
        """The review guide of the repository at `root`, read from its base branch's commit.

        A guide edited on a ticket's branch, or not committed, is not read, so a branch cannot
        change the guide it is reviewed by. None when the base commits no guide or an empty one.
        """
        found = await self._git.show_on_base(root, REVIEW_GUIDE_FILE)
        if found is None:
            return None
        text = found[1].strip()
        return ReviewGuide(base=found[0], text=text) if text else None

    async def grant_intake_key(self, name: str, repository: Path, url: str) -> IntakeGrant:
        """Record that tracker key `name` may serve `repository` at `url`, replacing a row."""
        if not key_name(name):
            msg = (
                f"{name!r} is not an intake key name: "
                f"{INTAKE_KEY_PREFIX} then capitals, digits or _"
            )
            raise BadRequestError(msg)
        address = url.rstrip("/")
        if "#" in address or not any(
            tracker_allowed(tracker, address) for tracker in ("linear", "jira", "slack")
        ):
            msg = (
                f"{url!r} is not an address a tracker key may go to: "
                "https://api.linear.app/graphql, an https://<site>.atlassian.net address, "
                "https://slack.com/api or one on this machine"
            )
            raise BadRequestError(msg)
        async with self._uow() as session:
            return await GrantRepository(session).upsert(
                IntakeGrant(key_name=name, repository=str(repository), url=address)
            )

    async def intake_grant(self, name: str) -> IntakeGrant | None:
        """The grant of a tracker key, None when this machine holds none."""
        async with self._uow() as session:
            return await GrantRepository(session).get(name)

    async def revoke_intake_key(self, name: str) -> bool:
        """Delete the grant of a tracker key; whether there was one."""
        async with self._uow() as session:
            return await GrantRepository(session).delete(name)

    async def list_intake_grants(self) -> list[IntakeGrant]:
        """Every grant, ordered by key name."""
        async with self._uow() as session:
            return await GrantRepository(session).list_all()

    async def board_settings(self) -> BoardSettings:
        """The board-wide settings; a key never set reads None."""
        async with self._uow() as session:
            return await BoardSettingsRepository(session).read()

    async def set_board_setting(self, key: str, value: int | None) -> BoardSettings:
        """Set a board-wide setting to a whole number of 0 or more, or clear it with None."""
        if key not in BOARD_SETTING_KEYS:
            raise BadRequestError(f"unknown board setting {key}: agent_slots or prune_days")
        if value is not None and not _whole(value):
            raise BadRequestError(f"{key} is a whole number of 0 or more, not {value}")
        async with self._uow() as session:
            repository = BoardSettingsRepository(session)
            await repository.write(key, value)
            return await repository.read()

    async def check_exceptions(
        self, root: Path, *, today: date | None = None, base_ref: str | None = None
    ) -> ExceptionsReport:
        """The problems of `exceptions.toml` (`ConfigChecks.check_exceptions`)."""
        return await self._checks.check_exceptions(root, today=today, base_ref=base_ref)

    async def check_config(self, root: Path) -> ConfigReport:
        """The problems of `config.toml` (`ConfigChecks.check_config`)."""
        return await self._checks.check_config(root)

    async def check_repository(self, root: Path) -> ConfigReport:
        """`check_config`, `check_exceptions` and the templates (`ConfigChecks`)."""
        return await self._checks.check_repository(root)


__all__ = ["CONFIG_FILE", "EXCEPTIONS_FILE", "REVIEW_GUIDE_FILE", "TIMED_OUT", "SettingsService"]
