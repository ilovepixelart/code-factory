"""Reading files below a root without following links."""

import os
from pathlib import Path

import pytest

from code_factory.git.service import GitService
from code_factory.platform.errors import BadRequestError


async def test_a_plain_file_is_read_and_a_missing_one_is_none(
    service: GitService, tmp_path: Path
) -> None:
    (tmp_path / "d").mkdir()
    (tmp_path / "d/x.md").write_text("héllo\n", encoding="utf-8")
    assert await service.read_text_below(tmp_path, "d/x.md", 100) == "héllo\n"
    assert await service.read_text_below(tmp_path, "d/missing.md", 100) is None


@pytest.mark.parametrize("relative", ["../x", "/etc/passwd", "a/../x", ""])
async def test_a_path_that_climbs_or_is_absolute_is_refused(
    service: GitService, tmp_path: Path, relative: str
) -> None:
    with pytest.raises(BadRequestError):
        await service.read_text_below(tmp_path, relative, 100)


async def test_links_fifos_big_and_binary_files_are_refused(
    service: GitService, tmp_path: Path
) -> None:
    (tmp_path / "real.txt").write_text("secret\n")
    (tmp_path / "link.txt").symlink_to(tmp_path / "real.txt")
    (tmp_path / "dir").mkdir()
    (tmp_path / "dirlink").symlink_to(tmp_path / "dir")
    (tmp_path / "dir/in.txt").write_text("x")
    os.mkfifo(tmp_path / "fifo")
    (tmp_path / "big.txt").write_text("x" * 101)
    (tmp_path / "bin").write_bytes(b"\xff\xfe")
    for relative, words in [
        ("link.txt", "a link"), ("dirlink/in.txt", "a link"), ("fifo", "not a regular file"),
        ("big.txt", "over 100 bytes"), ("bin", "not UTF-8"),
    ]:  # fmt: skip
        with pytest.raises(BadRequestError, match=words):
            await service.read_text_below(tmp_path, relative, 100)
    assert await service.read_text_below(tmp_path, "dir/in.txt", 100) == "x"


async def test_branch_refusal_and_merged_branch_pass_through(service: GitService) -> None:
    assert service.branch_refusal("a..b") == "it holds .., which git reads as a range"
    assert service.branch_refusal("ticket/cf-1") is None
    assert service.merged_branch("Merge pull request #7 from o/ticket/cf-7") == "ticket/cf-7"
    assert service.merged_branch("Merge branch 'x' into main") == "x"
    assert service.merged_branch("Fix a thing") is None


async def test_the_probe_passes_on_this_git(service: GitService) -> None:
    await service.probe()
