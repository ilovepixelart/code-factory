"""More defects a second reading found, at the service: a tracked file that cannot be read, a Slack
grant, the real home folder, an uncommitted change, an oversize lockfile and a linked worktree."""

from pathlib import Path, PurePosixPath

from code_factory.settings.adapters import GitFacts
from code_factory.settings.rules import config_problems, lenient_config
from code_factory.settings.rules.secrets import VALIDATION_HOME, container_mount_problem
from settings_support import agit, arepository


def test_an_absolute_mount_of_the_real_home_is_refused_like_its_tilde_form() -> None:
    homes = (VALIDATION_HOME, PurePosixPath("/Users/alex"))
    for entry in ("/Users/alex:/x", "/Users/alex/.ssh:/x", "/Users/alex/.ssh/keys:/x", "~/.ssh:/x"):
        assert container_mount_problem(entry, homes) is not None, entry
    assert container_mount_problem("/Users/alex/.cargo/registry:/x", homes) is None
    assert container_mount_problem("/Users/alex/.ssh:/x") is None  # the synthetic home alone


def test_the_checks_and_the_lenient_reading_take_the_real_home() -> None:
    homes = (VALIDATION_HOME, PurePosixPath("/Users/alex"))
    text = '[checks]\ncommand = "x"\ncontainer_mounts = ["/Users/alex/.ssh:/ssh"]\n'
    assert config_problems("c", text) == []
    assert [p.line for p in config_problems("c", text, homes)] == [3]
    synthetic = lenient_config(text).checks
    real = lenient_config(text, homes).checks
    assert synthetic is not None
    assert real is not None
    assert synthetic.container_mounts == ["/Users/alex/.ssh:/ssh"]
    assert real.container_mounts is None


async def test_the_main_checkout_of_a_linked_worktree_is_found(tmp_path: Path) -> None:
    root = await arepository(tmp_path / "main", {"a.txt": "a\n"})
    await agit(root, "commit", "-q", "-m", "c")
    linked = tmp_path / "linked"
    await agit(root, "worktree", "add", "-q", "-b", "wt", str(linked))
    facts = GitFacts()
    assert await facts.main_checkout(linked) == root.resolve()
    assert await facts.main_checkout(root) == root.resolve()
    assert await facts.main_checkout(tmp_path / "nowhere") is None
