"""Checking a repository's configuration: `config.toml`, `exceptions.toml` and its templates."""

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path, PurePosixPath

from code_factory.platform.db import UnitOfWork
from code_factory.settings.adapters import (
    Files,
    GitFacts,
    Sources,
    in_thread,
    local_resolver,
)
from code_factory.settings.adapters.scanning import scan_config
from code_factory.settings.models.errors import unjudged_message
from code_factory.settings.models.problems import (
    ConfigReport,
    ExceptionsReport,
    Problem,
    TicketFacts,
)
from code_factory.settings.repository import GrantRepository
from code_factory.settings.rules import (
    ExceptionFacts,
    exception_tickets,
    exceptions_problems,
    expiry_fails,
    intake_key_problems,
    lenient_config,
)
from code_factory.settings.rules.entries import read_exceptions
from code_factory.settings.rules.secrets import VALIDATION_HOME, Resolve, Unjudged
from code_factory.settings.rules.templates import (
    AGENTS_FOLDER,
    CONFIG_BYTES,
    TEMPLATE_BYTES,
    TEMPLATES_FOLDER,
    template_problem,
    unreadable_message,
)
from code_factory.settings.service.paths import (
    CONFIG_FILE,
    EXCEPTIONS_FILE,
    TIMED_OUT,
)


def resolver_for(homes: tuple[PurePosixPath, ...], root: Path) -> Resolve:
    """Links are followed below the real home and the repository, nowhere else.

    `VALIDATION_HOME` is only where secrets are named: `/home` can be an automount map.
    """
    real = [home for home in homes[1:] if home != VALIDATION_HOME]
    return local_resolver((*real, PurePosixPath(root)))


class ConfigChecks:
    """The checks of a repository's configuration, over the settings' own files, git and records."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Callable[[], datetime],
        files: Files,
        git: GitFacts,
        homes: tuple[PurePosixPath, ...],
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._files = files
        self._git = git
        self._sources = Sources(files, git)
        self._homes = homes
        self._tickets: TicketFacts | None = None

    def bind_ticket_facts(self, facts: TicketFacts) -> None:
        """Let the exceptions check ask whether the tickets its entries name exist."""
        self._tickets = facts

    async def check_exceptions(
        self, root: Path, *, today: date | None = None, base_ref: str | None = None
    ) -> ExceptionsReport:
        """The problems of `exceptions.toml` against the tool files, lockfiles, tests and tickets.

        `today` defaults to the clock's date. An expired entry is a note, not a problem, on a
        branch that changed none of the files it speaks for. `unchecked` lists the checks that
        could not run.
        """
        text = await self._files.read_below(root, EXCEPTIONS_FILE, CONFIG_BYTES)
        if text is None:
            if await self._files.present(root, EXCEPTIONS_FILE):
                unreadable = Problem(EXCEPTIONS_FILE, 0, unreadable_message(CONFIG_BYTES))
                return ExceptionsReport((unreadable,), (), self._unchecked())
            text = ""
        today = today or self._clock().date()
        existing = None
        if self._tickets is not None:
            ids = exception_tickets(text)
            existing = await self._tickets.existing(ids) if ids else frozenset()
        entries, _ = read_exceptions(text, existing)
        sharing = {}
        for entry in (e for e in entries if e.kind == "age"):
            if self._tickets is not None:
                sharing[entry.ticket] = await self._tickets.sharing_branch(entry.ticket)
        locked, lock_problems = await self._sources.locked(root, entries)
        fails = True
        if any(today >= e.expires for e in entries):
            fork = await self._git.fork(root, base_ref)
            fails = expiry_fails(fork.base, fork.head, fork.changed)
        facts = ExceptionFacts(
            tickets=existing,
            expiry_fails=fails,
            tools=await self._sources.tool_files(root),
            locked=locked,
            sharing=sharing,
            tests=await self._sources.tests(root, entries),
        )
        report = exceptions_problems(text, today, facts)
        problems = tuple(sorted([*report.problems, *lock_problems]))
        return ExceptionsReport(problems, report.notes, self._unchecked())

    def _unchecked(self) -> tuple[str, ...]:
        return () if self._tickets is not None else ("ticket references",)

    async def _grant_problems(self, root: Path, text: str) -> list[Problem]:
        config = await in_thread(lenient_config, text, self._homes)
        if config is None:
            return [Problem(CONFIG_FILE, 0, TIMED_OUT)]
        intake = config.intake
        names = (
            [
                n
                for n in (intake.linear_token_env, intake.jira_token_env, intake.slack_token_env)
                if n is not None
            ]
            if intake
            else []
        )
        if not names:
            return []
        async with self._uow() as session:
            grants = await GrantRepository(session).get_many(names)
        found = await in_thread(intake_key_problems, config, text, grants, str(root))
        return [Problem(CONFIG_FILE, 0, TIMED_OUT)] if found is None else found

    async def check_config(self, root: Path) -> ConfigReport:
        """The problems of `config.toml`.

        Syntax, model, across keys, the automation templates the board must read, and tracker keys
        held on this machine for another repository or address.
        """
        text = await self._files.read_below(root, CONFIG_FILE, CONFIG_BYTES)
        if text is None:
            if await self._files.present(root, CONFIG_FILE):
                return ConfigReport((Problem(CONFIG_FILE, 0, unreadable_message(CONFIG_BYTES)),))
            return ConfigReport()
        try:
            scanned = await in_thread(
                scan_config, CONFIG_FILE, text, self._homes, resolver_for(self._homes, root)
            )
        except Unjudged as scan:
            return ConfigReport((Problem(CONFIG_FILE, 0, unjudged_message(scan.entries)),))
        if scanned is None:
            return ConfigReport((Problem(CONFIG_FILE, 0, TIMED_OUT),))
        problems, templates = scanned
        for index, template in templates:
            if await self._files.read_below(root, template, TEMPLATE_BYTES) is None:
                problems.append(template_problem(CONFIG_FILE, text, index, template))
        problems += await self._grant_problems(root, text)
        return ConfigReport(tuple(sorted(problems)))

    async def _text_file_problems(self, root: Path) -> list[Problem]:
        """Each `.md` file of the templates and agents folders that is not a readable text file."""
        found = []
        for folder in (TEMPLATES_FOLDER, AGENTS_FOLDER):
            for name in await self._files.names(root, folder):
                relative = f"{folder}/{name}"
                if (
                    name.endswith(".md")
                    and await self._files.read_below(root, relative, TEMPLATE_BYTES) is None
                ):
                    found.append(Problem(relative, 0, unreadable_message(TEMPLATE_BYTES)))
        return found

    async def check_repository(self, root: Path) -> ConfigReport:
        """`check_config`, `check_exceptions` and the templates, sorted by path and line.

        The notes and `unchecked` are those of `check_exceptions`.
        """
        config = await self.check_config(root)
        exceptions = await self.check_exceptions(root)
        problems = [*config.problems, *exceptions.problems, *await self._text_file_problems(root)]
        return ConfigReport(tuple(sorted(problems)), exceptions.notes, exceptions.unchecked)
