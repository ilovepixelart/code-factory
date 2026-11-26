"""`start`, `land`, `save`, `worktrees` and `git probe`: exit codes and the printed words."""

import argparse
from pathlib import Path

import pytest

from code_factory.git.cli import COMMANDS
from code_factory.git.service import GitService
from code_factory.platform.module import Command
from code_factory.platform.services import Services
from code_factory.repositories.service import RepositoryService
from git_support import Fakes, commit, ticket_ref, write


def command(name: str) -> Command:
    return next(c for c in COMMANDS if c.name == name)


@pytest.fixture
async def services(
    service: GitService,
    repositories: RepositoryService,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Services:
    await repositories.track(root)
    monkeypatch.chdir(root)
    registry = Services()
    registry.add(GitService, service)
    registry.add(RepositoryService, repositories)
    return registry


async def run(services: Services, name: str, *argv: str) -> int:
    parser = argparse.ArgumentParser(prog=name)
    cmd = command(name)
    cmd.configure(parser)
    assert cmd.run_async is not None
    return await cmd.run_async(parser.parse_args(argv), services)


def test_the_module_names_each_command() -> None:
    assert [c.name for c in COMMANDS] == ["start", "land", "save", "worktrees", "git"]


async def test_start_prints_the_path_and_branch(
    services: Services, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await run(services, "start", "CF-1") == 0
    assert capsys.readouterr().out == f"{root}/.code-factory/worktrees/CF-1 on ticket/cf-1\n"


async def test_save_prints_the_pushed_refs_or_why_not(
    services: Services, root: Path, fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    await run(services, "start", "CF-1")
    capsys.readouterr()
    tree = root / ".code-factory/worktrees/CF-1"
    commit(tree, "Work", **{"c.txt": "c\n"})
    assert await run(services, "save", "CF-1") == 0
    out = capsys.readouterr().out
    assert out.startswith("CF-1: saved ")
    # a hand worktree sends the ref only
    assert out.endswith(" at refs/wip/CF-1, pushed to origin: refs/wip/CF-1\n")
    fakes.held_ = "a token"
    write(tree, "w.txt", "w\n")
    assert await run(services, "save", "CF-1") == 1
    assert "saved here at " in capsys.readouterr().out


async def test_land_exits_1_when_any_is_not_merged_and_prints_the_words(
    services: Services, root: Path, fakes: Fakes, capsys: pytest.CaptureFixture[str]
) -> None:
    fakes.tickets["CF-2"] = ticket_ref("CF-2")
    await run(services, "start", "CF-1")
    commit(root / ".code-factory/worktrees/CF-1", "Work", **{"c.txt": "c\n"})
    capsys.readouterr()
    code = await run(services, "land", "CF-1", "CF-2")
    lines = capsys.readouterr().out.splitlines()
    assert code == 1
    assert lines[0].startswith("CF-1: merged https://example.test/pull/1")
    assert lines[1] == "CF-2: refused: no tree CF-2 for sample"


async def test_worktrees_list_remove_prune(
    services: Services, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    await run(services, "start", "CF-1")
    capsys.readouterr()
    assert await run(services, "worktrees", "list") == 0
    assert capsys.readouterr().out.startswith("CF-1 worktree ticket/cf-1 ahead=0 uncommitted=0")
    (root / ".code-factory/worktrees/stray").mkdir()
    assert await run(services, "worktrees", "prune") == 0
    assert capsys.readouterr().out == "pruned: 1 folders with no record, 0 left in the trash\n"


async def test_probe_prints_ok(services: Services, capsys: pytest.CaptureFixture[str]) -> None:
    assert await run(services, "git", "probe") == 0
    assert capsys.readouterr().out == "git ok\n"
