"""One ticket's page, the archive and the repository list over the real services."""

from code_factory.board.module import module

# Reads, and the savepoints a unit of work wraps them in.


def test_the_module_starts_no_background_work() -> None:
    assert module.background is None
