"""The service over a real git repository: the adapters read what the main checkout holds."""

from pathlib import Path

import pytest
from fastapi import FastAPI

from code_factory.app import MODULES
from code_factory.memory.models import EntryPatch, NewMemory
from code_factory.memory.service import MemoryService
from code_factory.memory_extras.adapters import DefinedTests, OriginWeb, RepositoryFiles
from code_factory.memory_extras.module import module
from code_factory.memory_extras.service import MemoryExtrasService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError
from git_support import Fakes, commit, git, make_repo, make_service
from memory_extras_fakes import FakeRepositories, FakeTickets
from memory_extras_values import NOW, OWNER

CLAUDE = "# Rules\n\n- Commits and pull requests carry no AI attribution of any kind.\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = make_repo(tmp_path)
    commit(
        repo,
        "Add tests and docs",
        **{
            "CLAUDE.md": CLAUDE,
            "docs__notes.md": "The gate refuses a push whose checks did not pass.\n",
            "tests__test_gate.py": "def test_guarded():\n    pass\n\n\ndef helper():\n    pass\n",
            "src__kept.py": "x = 1\n",
        },
    )
    git(repo, "remote", "set-url", "origin", "git@github.com:owner/name.git")
    return repo


@pytest.fixture
def stack(uow: UnitOfWork, root: Path) -> tuple[MemoryExtrasService, MemoryService]:
    """The service over real git, and the memory service whose admission it registered."""
    git_service = make_service(uow, Fakes(roots={"sample": root}))
    memory = MemoryService(uow, clock=lambda: NOW)
    extras = MemoryExtrasService(
        uow,
        memory,
        FakeTickets(),
        FakeRepositories("sample", base=root.parent),
        RepositoryFiles(git_service),
        DefinedTests(git_service),
        OriginWeb(git_service),
        clock=lambda: NOW,
    )
    memory.add_preparation(extras.prepare_admission)
    return extras, memory


async def test_a_guard_naming_a_test_the_checkout_defines_is_enforced_and_a_helper_is_not(
    stack: tuple[MemoryExtrasService, MemoryService],
) -> None:
    service, memory = stack
    for name, guard in (("2026-10-01-a", "test_guarded"), ("2026-10-02-b", "helper")):
        patch = EntryPatch(
            repository="sample",
            id=name,
            fields={
                "kind": "lesson",
                "statement": name,
                "source": "chat",
                "date": name[:10],
                "guard": guard,
            },
        )
        await memory.apply([patch], by=OWNER)
    page = await service.page("", now=NOW)
    states = {r.id: (r.guard_state, r.loaded) for r in page.unreviewed}
    assert states == {"2026-10-01-a": ("enforced", False), "2026-10-02-b": ("missing", True)}


async def test_a_statement_restating_the_checkouts_claude_md_is_refused(
    stack: tuple[MemoryExtrasService, MemoryService],
) -> None:
    _, memory = stack
    said = NewMemory(
        repository="sample",
        kind="rule",
        statement="Commits and pull requests carry no AI attribution of any kind",
        source="chat",
    )
    with pytest.raises(BadRequestError, match=r"^restates CLAUDE.md line 3"):
        await memory.add(said, by=OWNER)


async def test_the_search_reads_the_tracked_documents_and_a_cite_is_checked_on_disk(
    stack: tuple[MemoryExtrasService, MemoryService],
) -> None:
    service, memory = stack
    fields = {"kind": "rule", "statement": "Cites two", "source": "chat", "date": "2026-11-01"}
    fields["cites"] = ["src/kept.py", "src/removed.py", "test_guarded"]
    await memory.apply(
        [EntryPatch(repository="sample", id="2026-11-01-cites", fields=fields)], by=OWNER
    )
    found, matched = await service.knowledge("sample", "gate", 10)
    assert (matched, [(f.path, f.open) for f in found]) == (
        1,
        [("docs/notes.md", "https://github.com/owner/name/blob/HEAD/docs/notes.md")],
    )
    page = await service.page("", now=NOW)
    assert page.unreviewed[0].stale_cites == ["src/removed.py"]


def test_the_module_is_registered_and_adds_the_memory_command() -> None:
    assert module in MODULES
    assert [c.name for c in module.commands] == ["memory"]


async def test_the_application_registers_the_admission_on_the_memory_service(app: FastAPI) -> None:
    services = app.state.services
    assert isinstance(services.get(MemoryExtrasService), MemoryExtrasService)
    memory = services.get(MemoryService)
    first = "Always rebase ticket branches onto main before landing"
    await memory.add(
        NewMemory(repository="loose", kind="rule", statement=first, source="chat"), by=OWNER
    )
    second = NewMemory(
        repository="loose",
        kind="rule",
        statement="Never rebase ticket branches onto main",
        source="chat",
    )
    with pytest.raises(
        ConflictError, match=r"^it is on the subject of 2026-\d\d-\d\d-always-rebase"
    ):
        await memory.add(second, by=OWNER, check_pairs=True)
