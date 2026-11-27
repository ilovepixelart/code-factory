"""The Codex CLI version the catalog is asked with: read from a trusted `codex --version`."""

from pathlib import Path

import pytest

from code_factory.agents.adapters import probe


def _codex(folder: Path, says: str) -> None:
    program = folder / "codex"
    program.write_text(f"#!/bin/sh\necho '{says}'\n")
    program.chmod(0o755)


def _share(folder: Path) -> None:
    """Make `folder` a shared temporary folder: sticky and written by everyone, as /tmp is."""
    folder.chmod(0o1777)


@pytest.fixture
def bin_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The only PATH folder, one only the user can write."""
    folder = tmp_path / "bin"
    folder.mkdir(mode=0o755)
    monkeypatch.setenv("PATH", str(folder))
    return folder


@pytest.mark.parametrize(
    ("says", "version"),
    [
        ("codex-cli 0.123.0", "0.123.0"),
        ("codex-cli 0.124.0-alpha.2", "0.124.0-alpha.2"),
        ("codex-cli latest", ""),
        ("0.1", ""),
    ],
)
async def test_the_version_is_what_codex_prints_when_it_is_a_version(
    bin_folder: Path, says: str, version: str
) -> None:
    _codex(bin_folder, says)

    assert await probe.codex_version() == version


@pytest.mark.usefixtures("bin_folder")
async def test_no_codex_on_the_path_is_no_version() -> None:
    assert await probe.codex_version() == ""


async def test_a_codex_below_a_folder_everyone_may_write_is_never_started(
    bin_folder: Path,
) -> None:
    _codex(bin_folder, "codex-cli 0.123.0")
    _share(bin_folder.parent)

    assert await probe.codex_version() == ""
