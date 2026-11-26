"""A checks container mount is judged by the folder it reaches on disk, not by its spelling: a
doubled slash, a link or another case of a secret folder is refused, an unrelated folder is not."""

import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.settings.adapters import RESOLVE_WORKERS
from code_factory.settings.adapters import resolver as resolver_module
from code_factory.settings.rules import config as config_rules
from code_factory.settings.service import SettingsService
from settings_support import write

CONFIG = ".code-factory/config.toml"
REACHES = "the host folder is, holds or is in the home folder or a secret folder"


@pytest.fixture(autouse=True)
def _workers_idle() -> Iterator[None]:
    """The resolver worker budget is the process's: wait for abandoned workers to end."""
    yield
    for _ in range(RESOLVE_WORKERS):
        assert resolver_module._SLOTS.acquire(timeout=5)
    for _ in range(RESOLVE_WORKERS):
        resolver_module._SLOTS.release()


@pytest.fixture
def home(tmp_path: Path) -> Path:
    found = tmp_path / "home" / "alex"
    (found / ".ssh").mkdir(parents=True)
    (found / "work").mkdir()
    return found


@pytest.fixture
def service(uow: UnitOfWork, home: Path) -> SettingsService:
    return SettingsService(uow, clock=lambda: datetime(2026, 11, 2, tzinfo=UTC), home=home)


async def problems(service: SettingsService, tmp_path: Path, mount: str) -> list[str]:
    repo = tmp_path / "repo"
    write(repo, CONFIG, f'[checks]\ncommand = "x"\ncontainer_mounts = ["{mount}:/x"]\n')
    return [str(p) for p in (await service.check_config(repo)).problems]


async def test_a_doubled_leading_slash_does_not_hide_a_secret(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    found = await problems(service, tmp_path, f"/{home}/.ssh")
    assert [p.endswith(REACHES) for p in found] == [True]


async def test_a_link_into_a_secret_is_refused(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    link = tmp_path / "repo" / "innocent"
    link.parent.mkdir()
    link.symlink_to(home / ".ssh")
    found = await problems(service, tmp_path, str(link))
    assert [p.endswith(REACHES) for p in found] == [True]


async def test_a_link_to_the_home_folder_is_refused(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    link = tmp_path / "repo" / "shortcut"
    link.parent.mkdir()
    link.symlink_to(home)
    found = await problems(service, tmp_path, str(link))
    assert [p.endswith(REACHES) for p in found] == [True]


async def test_a_path_through_a_parent_step_is_refused(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    found = await problems(service, tmp_path, f"{home}/work/../.ssh")
    assert len(found) == 1


async def test_a_path_in_another_case_is_refused(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    found = await problems(service, tmp_path, str(home / ".SSH"))
    assert [p.endswith(REACHES) for p in found] == [True]


async def test_a_folder_outside_the_secrets_is_accepted_directly_and_through_a_link(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    link = tmp_path / "repo" / "cache-link"
    link.parent.mkdir()
    link.symlink_to(cache)
    assert await problems(service, tmp_path, str(cache)) == []
    assert await problems(service, tmp_path, str(link)) == []
    assert await problems(service, tmp_path, str(home / "work")) == []


async def test_a_link_retargeted_after_a_load_is_judged_again(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    repo = tmp_path / "repo"
    link = repo / "cache"
    link.parent.mkdir()
    link.symlink_to(home / "work")
    write(
        repo,
        CONFIG,
        '[checks]\ncommand = "x"\ncontainer_mounts = ["cache:/x"]\n'.replace("cache", str(link)),
    )
    first = await service.load(repo)
    assert first.checks is not None
    assert first.checks.container_mounts == [f"{link}:/x"]
    link.unlink()
    link.symlink_to(home / ".ssh")
    second = await service.load(repo)
    assert second.checks is not None
    assert second.checks.container_mounts is None


async def test_a_link_loop_is_refused(service: SettingsService, tmp_path: Path) -> None:
    loop = tmp_path / "repo" / "loop"
    loop.parent.mkdir()
    loop.symlink_to(loop)
    found = await problems(service, tmp_path, str(loop))
    assert [p.endswith(REACHES) for p in found] == [True]


async def test_a_key_spelled_with_an_escape_is_still_judged_again_on_every_load(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    repo = tmp_path / "repo"
    link = repo / "cache"
    link.parent.mkdir()
    link.symlink_to(home / "work")
    write(
        repo,
        CONFIG,
        f'[checks]\ncommand = "x"\n"container\\u005fmounts" = ["{link}:/x"]\n',
    )
    first = await service.load(repo)
    assert first.checks is not None
    assert first.checks.container_mounts == [f"{link}:/x"]
    link.unlink()
    link.symlink_to(home / ".ssh")
    second = await service.load(repo)
    assert second.checks is not None
    assert second.checks.container_mounts is None


async def test_a_check_resolves_the_mounts_once(
    service: SettingsService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[object] = []

    def counting(roots):  # noqa: ANN001, ANN202
        built.append(roots)
        return lambda path: path

    monkeypatch.setattr("code_factory.settings.service.checks.local_resolver", counting)
    await problems(service, tmp_path, str(tmp_path / "repo" / "cache"))
    assert len(built) == 1


async def test_a_directory_holding_a_linked_secret_file_is_refused(
    service: SettingsService, tmp_path: Path, home: Path
) -> None:
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    (dotfiles / "config.json").write_text("{}")
    (home / ".docker").mkdir()
    (home / ".docker" / "config.json").symlink_to(dotfiles / "config.json")
    found = await problems(service, tmp_path, str(home / ".docker"))
    assert [p.endswith(REACHES) for p in found] == [True]


async def test_a_load_parses_the_config_off_the_event_loop(
    service: SettingsService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop_thread = threading.get_ident()
    parsers: list[int] = []
    real = config_rules.parse_toml

    def recording(text: str):  # noqa: ANN202
        parsers.append(threading.get_ident())
        return real(text)

    monkeypatch.setattr(config_rules, "parse_toml", recording)
    repo = tmp_path / "repo"
    write(repo, CONFIG, '[checks]\ncommand = "x"\ncontainer_mounts = ["/srv/a:/x"]\n')
    await service.load(repo)
    assert parsers
    assert loop_thread not in parsers
