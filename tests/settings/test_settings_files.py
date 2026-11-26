"""Reading a file below a repository root: no link followed, a size cap, valid UTF-8 or the file
reads as missing. The size boundaries are the previous implementation's template limit."""

import errno
import os
from pathlib import Path

import pytest

from code_factory.settings.adapters import Files, FileTimedOut
from code_factory.settings.adapters import files as files_module

LIMIT = 64 * 1024


@pytest.fixture
def files() -> Files:
    return Files()


async def test_a_file_below_the_root_is_read(files: Files, tmp_path: Path) -> None:
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "c.md").write_text("héllo\n", encoding="utf-8")
    assert await files.read_below(tmp_path, "a/b/c.md", LIMIT) == "héllo\n"


async def test_a_root_that_is_itself_a_link_is_followed(files: Files, tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "x.md").write_text("x")
    (tmp_path / "link").symlink_to(real)
    assert await files.read_below(tmp_path / "link", "x.md", LIMIT) == "x"


@pytest.mark.parametrize(
    "name", ["missing.md", "dir", "", ".", "a/../x.md", "/etc/hosts", "../x.md"]
)
async def test_a_name_that_is_no_file_below_the_root_reads_as_missing(
    files: Files, tmp_path: Path, name: str
) -> None:
    (tmp_path / "dir").mkdir()
    (tmp_path / "x.md").write_text("x")
    assert await files.read_below(tmp_path / "dir", name, LIMIT) is None


async def test_a_file_that_is_a_link_is_refused(files: Files, tmp_path: Path) -> None:
    (tmp_path / "target.md").write_text("secret")
    (tmp_path / "link.md").symlink_to(tmp_path / "target.md")
    assert await files.read_below(tmp_path, "link.md", LIMIT) is None
    assert await files.read_below(tmp_path, "target.md", LIMIT) == "secret"


async def test_a_file_below_a_linked_folder_is_refused(files: Files, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.md").write_text("secret")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "templates").symlink_to(outside)
    assert await files.read_below(repo, "templates/x.md", LIMIT) is None


async def test_the_size_cap_is_inclusive(files: Files, tmp_path: Path) -> None:
    (tmp_path / "at.md").write_bytes(b"a" * LIMIT)
    (tmp_path / "over.md").write_bytes(b"a" * (LIMIT + 1))
    assert await files.read_below(tmp_path, "at.md", LIMIT) == "a" * LIMIT
    assert await files.read_below(tmp_path, "over.md", LIMIT) is None


async def test_text_that_is_not_utf8_reads_as_missing(files: Files, tmp_path: Path) -> None:
    (tmp_path / "bin.md").write_bytes(b"ok \xff\xfe")
    assert await files.read_below(tmp_path, "bin.md", LIMIT) is None


async def test_a_fifo_reads_as_missing_without_blocking(files: Files, tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe.md")
    assert await files.read_below(tmp_path, "pipe.md", LIMIT) is None
    assert await files.stat(tmp_path, "pipe.md") is None


async def test_the_stat_key_changes_with_the_size_the_mtime_and_the_file(
    files: Files, tmp_path: Path
) -> None:
    path = tmp_path / "config.toml"
    path.write_text("a = 1\n")
    os.utime(path, ns=(10**18, 10**18))
    first = await files.stat(tmp_path, "config.toml")
    assert first is not None
    assert await files.stat(tmp_path, "config.toml") == first
    path.write_text("a = 12\n")
    os.utime(path, ns=(10**18, 10**18))
    resized = await files.stat(tmp_path, "config.toml")
    assert resized != first
    path.write_text("a = 13\n")
    os.utime(path, ns=(10**18 + 1, 10**18 + 1))
    assert await files.stat(tmp_path, "config.toml") not in {first, resized}
    replacement = tmp_path / "other"
    replacement.write_text("a = 14\n")
    os.utime(replacement, ns=(10**18 + 1, 10**18 + 1))
    before = await files.stat(tmp_path, "config.toml")
    replacement.replace(path)
    assert await files.stat(tmp_path, "config.toml") != before


async def test_a_missing_file_has_no_stat_key(files: Files, tmp_path: Path) -> None:
    assert await files.stat(tmp_path, "config.toml") is None


async def test_present_sees_a_link_that_read_refuses(files: Files, tmp_path: Path) -> None:
    (tmp_path / "target.md").write_text("x")
    (tmp_path / "link.md").symlink_to(tmp_path / "target.md")
    assert await files.present(tmp_path, "link.md") is True
    assert await files.present(tmp_path, "target.md") is True
    assert await files.present(tmp_path, "none.md") is False
    assert await files.present(tmp_path, "../x") is False


async def test_names_lists_a_folder_but_not_through_a_link(files: Files, tmp_path: Path) -> None:
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "b.md").write_text("")
    (tmp_path / "t" / "a.md").write_text("")
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "x.md").write_text("")
    (tmp_path / "l").symlink_to(tmp_path / "elsewhere")
    assert await files.names(tmp_path, "t") == ["a.md", "b.md"]
    assert await files.names(tmp_path, "l") == []
    assert await files.names(tmp_path, "none") == []
    assert await files.names(tmp_path, "t/a.md") == []


@pytest.mark.parametrize("call", ["_open_below", "_read"])
async def test_a_timeout_reported_by_the_filesystem_is_a_timeout_not_a_missing_file(
    files: Files, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, call: str
) -> None:
    (tmp_path / "x.md").write_text("x")
    real = os.open if call == "_open_below" else os.read
    name = "open" if call == "_open_below" else "read"

    def stalled(*_args: object, **_kwargs: object) -> int:
        raise TimeoutError(errno.ETIMEDOUT, "Connection timed out")

    monkeypatch.setattr(files_module.os, name, stalled)
    assert await files.read_below(tmp_path, "x.md", LIMIT) is None
    with pytest.raises(FileTimedOut):
        await files.read_below(tmp_path, "x.md", LIMIT, strict=True)
    monkeypatch.setattr(files_module.os, name, real)
    assert await files.read_below(tmp_path, "x.md", LIMIT, strict=True) == "x"
