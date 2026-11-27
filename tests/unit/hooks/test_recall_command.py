"""`code-factory recall`: what a session starting in a folder is given, and never a failure."""

import argparse
import io
import sys
from pathlib import Path
from typing import cast

import pytest

from code_factory.hooks.cli import commands
from code_factory.hooks.models import RecalledText
from code_factory.hooks.service import HookService
from code_factory.platform.services import Services

RECALL = next(command for command in commands if command.name == "recall")


class _Hooks:
    def __init__(self, answer: RecalledText | Exception | None) -> None:
        self.answer = answer
        self.asked: list[tuple[str, object]] = []

    async def recall(self, *, cwd: str, actor: object) -> RecalledText | None:
        self.asked.append((cwd, actor))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


async def _recall(
    monkeypatch: pytest.MonkeyPatch, stdin: str, hooks: _Hooks
) -> tuple[int, list[tuple[str, object]]]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    services = Services()
    services.add(HookService, cast("HookService", hooks))
    assert RECALL.run_async is not None
    code = await RECALL.run_async(argparse.Namespace(), services)
    return code, hooks.asked


async def test_the_recalled_text_for_the_payloads_folder_is_printed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hooks = _Hooks(RecalledText(text="remember this\n", memory_kept=1, ticket_kept=0))

    code, asked = await _recall(monkeypatch, '{"cwd": "/work/tree"}', hooks)

    assert (code, asked, capsys.readouterr().out) == (0, [("/work/tree", None)], "remember this\n")


async def test_an_empty_payload_recalls_for_the_current_folder(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    code, asked = await _recall(monkeypatch, "", _Hooks(None))

    assert (code, asked, capsys.readouterr().out) == (0, [(str(tmp_path), None)], "")


@pytest.mark.parametrize(
    ("stdin", "answer", "asked"),
    [
        ("[1, 2]", None, []),  # not an object: nothing is asked
        ("{not json", None, []),
        ('{"cwd": "/w"}', RuntimeError("the board is down"), [("/w", None)]),
    ],
)
async def test_a_payload_or_recall_that_fails_prints_nothing_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stdin: str,
    answer: Exception | None,
    asked: list[tuple[str, object]],
) -> None:
    code, seen = await _recall(monkeypatch, stdin, _Hooks(answer))

    assert (code, seen, capsys.readouterr().out) == (0, asked, "")
