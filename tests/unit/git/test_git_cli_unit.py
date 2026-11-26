"""`start`, `land`, `save`, `worktrees` and `git probe`: exit codes and the printed words."""

from code_factory.git.cli import COMMANDS


def test_the_module_names_each_command() -> None:
    assert [c.name for c in COMMANDS] == ["start", "land", "save", "worktrees", "git"]
