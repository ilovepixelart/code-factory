"""F13 pass_rate and the scorer card view, with the evals oracle pairs."""

from code_factory.factory.models import ScorerCard, ScorerCards
from code_factory.factory.rules.scorers import pass_rate, scorer_views


def test_three_yes_one_no_one_unclear_pass_three_quarters() -> None:
    assert pass_rate(3, 1) == 0.75


def test_three_yes_two_no_pass_three_fifths() -> None:
    assert pass_rate(3, 2) == 0.6


def test_no_yes_and_no_answers_have_no_pass_rate() -> None:
    assert pass_rate(0, 0) is None


def test_only_no_answers_pass_nothing() -> None:
    assert pass_rate(0, 4) == 0.0


def card(yes: int, no: int, unclear: int) -> ScorerCard:
    return ScorerCard(
        repository="sample",
        name="ran-tests",
        question="Did the agent run the tests before finishing?",
        yes=yes,
        no=no,
        unclear=unclear,
        average_score=None,
        window_since=1793664000.0,
        window_until=1794268800.0,
    )


def test_a_card_is_shown_with_asked_pass_rate_and_window() -> None:
    got = scorer_views(ScorerCards(available=True, cards=[card(3, 1, 1)]))
    assert got.model_dump(mode="json", by_alias=True) == {
        "available": True,
        "cards": [
            {
                "repository": "sample",
                "name": "ran-tests",
                "question": "Did the agent run the tests before finishing?",
                "yes": 3,
                "no": 1,
                "unclear": 1,
                "asked": 5,
                "pass_rate": 0.75,
                "average_score": None,
                "window": {"from": 1793664000.0, "to": 1794268800.0},
            }
        ],
    }


def test_unclear_answers_count_as_asked_but_neither_side_of_the_rate() -> None:
    (view,) = scorer_views(ScorerCards(available=True, cards=[card(0, 0, 2)])).cards
    assert (view.asked, view.pass_rate) == (2, None)


def test_an_unavailable_provider_shows_no_cards() -> None:
    got = scorer_views(ScorerCards(available=False))
    assert (got.available, got.cards) == (False, [])
