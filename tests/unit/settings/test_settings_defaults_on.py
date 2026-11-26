"""Shipping and reviewing are on unless a repository's config turns them off (headache free)."""

import pytest

from code_factory.settings.models.config import AgentsTable, reviews, ships


@pytest.mark.parametrize("agents", [None, AgentsTable()])
def test_with_nothing_set_a_repository_ships_and_reviews(agents: AgentsTable | None) -> None:
    assert ships(agents)
    assert reviews(agents)


def test_false_turns_each_off_on_its_own() -> None:
    assert not ships(AgentsTable(ship=False))
    assert reviews(AgentsTable(ship=False))
    assert not reviews(AgentsTable(review=False))
    assert ships(AgentsTable(review=False))


def test_true_keeps_each_on() -> None:
    assert ships(AgentsTable(ship=True))
    assert reviews(AgentsTable(review=True))
