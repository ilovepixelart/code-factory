"""Claude Code's agent files: global then project folders closest first, links not followed,
a file over 256 KiB unread, a relative global folder refused."""

import os
from pathlib import Path

import pytest

from code_factory.agents.adapters.files import ClaudeAgentFiles, default_claude_home
from code_factory.agents.models.claude_agents import Unread

GOOD = "---\nname: {name}\ndescription: d\n---\nbody\n"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def test_global_agents_come_first_then_each_project_folder_closest_first(
    tmp_path: Path,
) -> None:
    home = tmp_path / "claude"
    outer = tmp_path / "outer"
    inner = outer / "inner"
    write(home / "agents" / "g.md", GOOD.format(name="g"))
    write(outer / ".claude" / "agents" / "o.md", GOOD.format(name="o"))
    write(inner / ".claude" / "agents" / "i.md", GOOD.format(name="i"))
    found = await ClaudeAgentFiles(home).find([inner])
    assert [(a.name, a.place) for a in found.agents][:3] == [
        ("g", "global"),
        ("i", "inner"),
        ("o", "outer"),
    ]


async def test_a_file_that_is_not_an_agent_is_listed_unread_with_why(tmp_path: Path) -> None:
    home = tmp_path / "claude"
    write(home / "agents" / "a.md", "# not an agent\n")
    write(home / "agents" / "b.md", "---\ndescription: x\n---\n")
    write(home / "agents" / "notes.txt", "ignored")
    found = await ClaudeAgentFiles(home).find([])
    assert [(Path(u.path).name, u.why) for u in found.unread] == [
        ("a.md", "no front matter"),
        ("b.md", "name: missing"),
    ]
    assert found.agents == []


async def test_a_file_over_256_kib_is_unread_and_one_of_exactly_that_size_is_read(
    tmp_path: Path,
) -> None:
    home = tmp_path / "claude"
    head = GOOD.format(name="big")
    write(home / "agents" / "exact.md", head + "x" * (256 * 1024 - len(head)))
    write(home / "agents" / "over.md", head + "x" * (256 * 1024 - len(head) + 1))
    found = await ClaudeAgentFiles(home).find([])
    assert [a.name for a in found.agents] == ["big"]
    assert found.unread == [Unread(path=str(home / "agents" / "over.md"), why="too large")]


async def test_a_linked_file_or_folder_is_not_followed(tmp_path: Path) -> None:
    home = tmp_path / "claude"
    elsewhere = tmp_path / "elsewhere"
    write(elsewhere / "x.md", GOOD.format(name="x"))
    (home / "agents").mkdir(parents=True)
    (home / "agents" / "dir").symlink_to(elsewhere)
    (home / "agents" / "file.md").symlink_to(elsewhere / "x.md")
    found = await ClaudeAgentFiles(home).find([])
    assert (found.agents, found.unread) == ([], [])


async def test_a_relative_global_folder_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path / "agents" / "a.md", GOOD.format(name="a"))
    monkeypatch.chdir(tmp_path)
    found = await ClaudeAgentFiles(Path()).find([])
    assert (found.agents, found.unread) == ([], [])


async def test_only_regular_files_are_opened_so_a_named_pipe_cannot_hang_the_listing(
    tmp_path: Path,
) -> None:
    home = tmp_path / "claude"
    (home / "agents").mkdir(parents=True)
    os.mkfifo(home / "agents" / "pipe.md")
    write(home / "agents" / "ok.md", GOOD.format(name="ok"))
    found = await ClaudeAgentFiles(home).find([])
    assert [a.name for a in found.agents] == ["ok"]
    assert found.unread == []


def test_the_claude_config_folder_variable_moves_the_global_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "elsewhere"))
    assert default_claude_home() == tmp_path / "elsewhere"
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert default_claude_home().name == ".claude"


async def test_a_folder_shared_by_two_projects_lists_its_agents_once(tmp_path: Path) -> None:
    home = tmp_path / "claude"
    proj = tmp_path / "proj"
    write(proj / ".claude" / "agents" / "r.md", GOOD.format(name="r"))
    found = await ClaudeAgentFiles(home).find([proj / "x", proj / "y"])
    assert [(a.name, a.place) for a in found.agents] == [("r", "proj")]
