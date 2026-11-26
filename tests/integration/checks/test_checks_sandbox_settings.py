"""The srt settings the checks module builds: what a contained command may read, write and reach."""

import json
from pathlib import Path
from typing import Any

import pytest

from checks_support import REPO, write_config
from code_factory.agents.service import AgentService
from code_factory.checks.adapters.sandbox import KitSandbox
from code_factory.platform.db import UnitOfWork
from code_factory.repositories.service import RepositoryService
from code_factory.settings.service import SettingsService

REGISTRIES = ["pypi.org:443", "files.pythonhosted.org:443", "registry.npmjs.org:443"]


@pytest.fixture
def sandbox(uow: UnitOfWork, repositories: RepositoryService, state: Path) -> KitSandbox:
    return KitSandbox(AgentService(uow), SettingsService(uow), repositories, state)


async def tree_rules(
    sandbox: KitSandbox, tree: Path, tmp_path: Path, *, reaches_hosts: bool = False
) -> dict[str, Any]:
    made = await sandbox.tree_settings(
        REPO, tree, tmp_path / "check.log", tmp_path / "scratch", reaches_hosts=reaches_hosts
    )
    return json.loads(made)


async def test_a_check_writes_only_its_tree_and_scratch_reaches_no_host_and_reads_no_state(
    sandbox: KitSandbox, tmp_path: Path, state: Path
) -> None:
    tree = tmp_path / "linked"
    tree.mkdir()
    (tree / ".git").write_text("gitdir: elsewhere\n")
    rules = await tree_rules(sandbox, tree, tmp_path)

    assert rules["network"]["allowedDomains"] == []
    assert rules["filesystem"]["allowWrite"] == [str(tree), str(tmp_path / "scratch")]
    assert rules["filesystem"]["denyWrite"] == []
    assert str(state) in rules["filesystem"]["denyRead"]
    assert "~/.ssh" in rules["filesystem"]["denyRead"]
    assert rules["filesystem"]["allowRead"] == [str(tmp_path / "check.log")]


async def test_a_setup_reaches_the_package_registries_when_the_repository_names_no_host(
    sandbox: KitSandbox, tracked: Path, tmp_path: Path
) -> None:
    rules = await tree_rules(sandbox, tracked, tmp_path, reaches_hosts=True)
    assert rules["network"]["allowedDomains"] == REGISTRIES


async def test_a_setup_reaches_the_hosts_the_repository_names(
    sandbox: KitSandbox, tracked: Path, tmp_path: Path
) -> None:
    write_config(tracked, '[agents]\nallowed_domains = ["pkgs.example.com:443"]\n')
    rules = await tree_rules(sandbox, tracked, tmp_path, reaches_hosts=True)
    assert rules["network"]["allowedDomains"] == ["pkgs.example.com:443"]


async def test_a_checkout_of_its_own_may_not_write_the_boards_folder(
    sandbox: KitSandbox, tracked: Path, tmp_path: Path
) -> None:
    rules = await tree_rules(sandbox, tracked, tmp_path)
    assert rules["filesystem"]["denyWrite"] == [str(tracked / ".code-factory")]
    assert await sandbox.checkout_denials(REPO, tracked) == [tracked / ".code-factory"]


async def test_the_boards_git_in_a_tree_may_not_write_its_git_folder(
    sandbox: KitSandbox, tracked: Path, tmp_path: Path
) -> None:
    made = await sandbox.git_settings(REPO, tracked, tmp_path / "git.log", tmp_path / "scratch")
    rules = json.loads(made)
    assert rules["filesystem"]["denyWrite"] == [str(tracked / ".git")]
    assert rules["network"]["allowedDomains"] == []
