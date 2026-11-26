"""`code-factory release draft|show|edit|publish|list`: the exact lines the commands spec gives."""

import argparse
import io
import os
import sys
from pathlib import Path

import pytest

from code_factory.platform.errors import (
    BadRequestError,
    UnavailableError,
)
from code_factory.releases.adapters import MAX_BYTES, read_notes
from code_factory.releases.cli import release_command


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="release")
    release_command.configure(parser)
    return parser.parse_args(argv)


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


async def test_standard_input_is_read_only_up_to_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.BytesIO(b"x" * (2 * MAX_BYTES))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(stream))
    with pytest.raises(BadRequestError, match="is over 1 MiB"):
        await read_notes("-")
    assert stream.tell() == MAX_BYTES + 1
