"""A repository whose settings cannot be judged in time is a problem on the board, not a refusal."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI

from code_factory.board.module import board_sources
from code_factory.board.service import BoardService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.services import Services
from code_factory.settings.models import ConfigUnjudgedError
from code_factory.settings.service import SettingsService
from git_support import make_repo

NOW = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)
REASON = "could not judge container_mounts in time"


class Unjudged:
    """Settings that cannot judge one root and read every other as the real service does."""

    def __init__(self, real: SettingsService, root: Path) -> None:
        self._real = real
        self._root = root

    async def load(self, root: Path) -> Any:  # noqa: ANN401
        if root == self._root:
            raise ConfigUnjudgedError(REASON)
        return await self._real.load(root)


@pytest.fixture
async def broken(app: FastAPI, uow: UnitOfWork, tmp_path: Path) -> tuple[BoardService, Path]:
    sources = board_sources(cast("Services", app.state.services))
    root = make_repo(tmp_path, "broken")
    await sources.repositories.track(root)
    faulty = replace(sources, settings=cast("SettingsService", Unjudged(sources.settings, root)))
    return BoardService(faulty, uow, clock=lambda: NOW), root


@pytest.mark.usefixtures("board_ids")
async def test_the_board_names_the_repository_it_could_not_read_and_still_answers(
    broken: tuple[BoardService, Path],
) -> None:
    service, root = broken
    answer = json.loads((await service.board()).body)
    assert answer["problems"] == [
        {
            "repository": "broken",
            "file": ".code-factory/config.toml",
            "path": f"{root}/.code-factory/config.toml",
            "reason": REASON,
        }
    ]
    assert sum(len(cards) for cards in answer["columns"].values()) == 6


@pytest.mark.usefixtures("board_ids")
async def test_the_ticket_list_carries_the_same_problem(broken: tuple[BoardService, Path]) -> None:
    service, _ = broken
    answer = await service.tickets({})
    assert [p["repository"] for p in answer["problems"]] == ["broken"]


async def test_a_ticket_page_is_read_though_another_repository_is_unreadable(
    broken: tuple[BoardService, Path], board_ids: dict[str, str]
) -> None:
    service, _ = broken
    page = await service.ticket_page("sample", board_ids["A bug in flight"])
    assert page["ticket"]["id"] == board_ids["A bug in flight"]
