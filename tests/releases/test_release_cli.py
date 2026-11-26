"""`code-factory release draft|show|edit|publish|list`: the exact lines the commands spec gives."""

import argparse
import io
import os
import sys
from pathlib import Path

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnavailableError,
)
from code_factory.platform.services import Services
from code_factory.releases.adapters import MAX_BYTES, read_notes
from code_factory.releases.cli import release_command
from code_factory.releases.service import ReleaseService
from code_factory.repositories.service import RepositoryService
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService
from ticket_values import OWNER


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="release")
    release_command.configure(parser)
    return parser.parse_args(argv)


@pytest.fixture
async def root(tmp_path: Path, repositories: RepositoryService) -> Path:
    """The tracked checkout `sample`, which the command line is run from."""
    checkout = tmp_path / "sample"
    checkout.mkdir()
    await repositories.track(checkout)
    return checkout


@pytest.fixture
def services(
    uow: UnitOfWork,
    tickets: TicketService,
    repositories: RepositoryService,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Services:
    monkeypatch.chdir(root)
    registry = Services()
    registry.add(ReleaseService, ReleaseService(uow, tickets))
    registry.add(RepositoryService, repositories)
    return registry


async def run(services: Services, *argv: str) -> int:
    run_async = release_command.run_async
    assert run_async is not None
    return await run_async(_parse(*argv), services)


async def test_draft_says_what_it_drafted_and_show_prints_the_notes(
    services: Services, tickets: TicketService, capsys: pytest.CaptureFixture[str]
) -> None:
    made = await tickets.create(NewTicket(repository="sample", title="Add a page"), by=OWNER)
    await tickets.set_merged(made.id, True, by=OWNER)
    assert await run(services, "draft", "1.0.0") == 0
    assert capsys.readouterr().out == "drafted sample 1.0.0\n"
    assert await run(services, "show", "1.0.0") == 0
    assert capsys.readouterr().out == f"# 1.0.0\n\n## Added\n- {made.id}: Add a page\n"


async def test_the_repository_is_the_tracked_one_the_current_folder_is_in(
    services: Services, capsys: pytest.CaptureFixture[str], root: Path, tmp_path: Path
) -> None:
    await run(services, "draft", "0.1.0")
    assert capsys.readouterr().out == "drafted sample 0.1.0\n"
    await run(services, "draft", "0.2.0", "--repository", str(root))
    assert capsys.readouterr().out == "drafted sample 0.2.0\n"
    await run(services, "list", "--repository", str(tmp_path / "sample"))
    assert capsys.readouterr().out == "0.2.0 draft 0 tickets\n0.1.0 draft 0 tickets\n"


async def test_a_subfolder_of_the_checkout_is_the_checkout(
    services: Services,
    capsys: pytest.CaptureFixture[str],
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deep = root / "src" / "pkg"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    await run(services, "draft", "0.1.0")
    assert capsys.readouterr().out == "drafted sample 0.1.0\n"


async def test_a_worktree_inside_the_checkout_is_the_checkout(
    services: Services, capsys: pytest.CaptureFixture[str], root: Path
) -> None:
    worktree = root / ".code-factory" / "worktrees" / "CF-12"
    worktree.mkdir(parents=True)
    await run(services, "draft", "0.1.0", "--repository", str(worktree))
    assert capsys.readouterr().out == "drafted sample 0.1.0\n"


async def test_the_innermost_tracked_checkout_wins(
    services: Services,
    repositories: RepositoryService,
    capsys: pytest.CaptureFixture[str],
    root: Path,
) -> None:
    inner = root / "vendor" / "inner"
    inner.mkdir(parents=True)
    await repositories.track(inner)
    await run(services, "draft", "0.1.0", "--repository", str(inner))
    assert capsys.readouterr().out == "drafted inner 0.1.0\n"


async def test_a_folder_of_no_tracked_repository_is_refused_and_drafts_nothing(
    services: Services, tmp_path: Path
) -> None:
    stray = tmp_path / "my-repo"
    stray.mkdir()
    with pytest.raises(NotFoundError, match=r"my-repo is not inside a tracked repository"):
        await run(services, "draft", "0.1.0", "--repository", str(stray))
    assert await services.get(ReleaseService).list(None) == []


async def test_a_sibling_folder_with_the_checkouts_name_as_prefix_is_not_inside_it(
    services: Services, tmp_path: Path
) -> None:
    sibling = tmp_path / "sample-two"
    sibling.mkdir()
    with pytest.raises(NotFoundError, match="is not inside a tracked repository"):
        await run(services, "draft", "0.1.0", "--repository", str(sibling))


async def test_edit_reads_the_notes_from_a_file(
    services: Services, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    await run(services, "draft", "1.0.0")
    notes = tmp_path / "notes.md"
    notes.write_text("# 1.0.0\n\nWords with ünïcode.\n", encoding="utf-8")
    capsys.readouterr()
    assert await run(services, "edit", "1.0.0", "--file", str(notes)) == 0
    assert capsys.readouterr().out == "edited 1.0.0\n"
    await run(services, "show", "1.0.0")
    assert capsys.readouterr().out == "# 1.0.0\n\nWords with ünïcode.\n"


async def test_edit_reads_the_notes_from_standard_input_with_a_dash(
    services: Services, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    await run(services, "draft", "1.0.0")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"# 1.0.0\n\nPiped.\n")))
    capsys.readouterr()
    await run(services, "edit", "1.0.0", "--file", "-")
    await run(services, "show", "1.0.0")
    assert capsys.readouterr().out == "edited 1.0.0\n# 1.0.0\n\nPiped.\n"


async def test_edit_refuses_a_file_that_is_missing_or_not_text(
    services: Services, tmp_path: Path
) -> None:
    await run(services, "draft", "1.0.0")
    with pytest.raises(NotFoundError, match="no such file"):
        await run(services, "edit", "1.0.0", "--file", str(tmp_path / "x"))
    binary = tmp_path / "bin"
    binary.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(BadRequestError, match="is not UTF-8 text"):
        await run(services, "edit", "1.0.0", "--file", str(binary))


async def test_edit_refuses_a_file_over_a_mebibyte(services: Services, tmp_path: Path) -> None:
    await run(services, "draft", "1.0.0")
    big = tmp_path / "big.md"
    big.write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(BadRequestError, match="is over 1 MiB"):
        await run(services, "edit", "1.0.0", "--file", str(big))


async def test_a_file_of_exactly_a_mebibyte_is_read(tmp_path: Path) -> None:
    exact = tmp_path / "exact.md"
    exact.write_bytes(b"x" * MAX_BYTES)
    assert len(await read_notes(str(exact))) == MAX_BYTES


async def test_a_file_that_never_answers_gives_up_with_a_sentence(tmp_path: Path) -> None:
    stalled = tmp_path / "stalled"
    os.mkfifo(stalled)  # opening it for reading blocks until a writer opens it
    try:
        with pytest.raises(UnavailableError, match=r"did not answer within 0\.2 s"):
            await read_notes(str(stalled), timeout_s=0.2)
    finally:
        os.close(os.open(stalled, os.O_WRONLY))  # lets the blocked reader thread finish


def test_list_takes_no_version() -> None:
    with pytest.raises(SystemExit):
        _parse("list", "1.0.0")


def test_edit_needs_a_file() -> None:
    with pytest.raises(SystemExit):
        _parse("edit", "1.0.0")


async def test_publish_counts_the_tickets_that_leave_the_board(
    services: Services, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    await run(services, "draft", "1.0.0")
    notes = tmp_path / "n.md"
    notes.write_text("See CF-1, CF-2 and CF-12.\n", encoding="utf-8")
    await run(services, "edit", "1.0.0", "--file", str(notes))
    capsys.readouterr()
    assert await run(services, "publish", "1.0.0") == 0
    assert capsys.readouterr().out == "published 1.0.0: 3 tickets leave the board\n"
    with pytest.raises(ConflictError, match="published already"):
        await run(services, "publish", "1.0.0")


async def test_list_prints_a_line_per_release_newest_first(
    services: Services, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    await run(services, "draft", "0.9.0")
    await run(services, "draft", "0.10.0")
    notes = tmp_path / "n.md"
    notes.write_text("CF-1\n", encoding="utf-8")
    await run(services, "edit", "0.9.0", "--file", str(notes))
    await run(services, "publish", "0.9.0")
    capsys.readouterr()
    assert await run(services, "list") == 0
    assert capsys.readouterr().out == "0.10.0 draft 0 tickets\n0.9.0 published 1 tickets\n"


async def test_list_of_a_repository_with_no_release_prints_nothing(
    services: Services, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await run(services, "list") == 0
    assert capsys.readouterr().out == ""


async def test_show_of_an_unknown_version_says_how_to_draft_it(services: Services) -> None:
    with pytest.raises(NotFoundError, match=r"draft it with code-factory release draft 3\.0\.0"):
        await run(services, "show", "3.0.0")


async def test_standard_input_is_read_only_up_to_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.BytesIO(b"x" * (2 * MAX_BYTES))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(stream))
    with pytest.raises(BadRequestError, match="is over 1 MiB"):
        await read_notes("-")
    assert stream.tell() == MAX_BYTES + 1
