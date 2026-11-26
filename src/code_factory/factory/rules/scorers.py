"""F13 the pass rate of a scorer and its card as the page shows it."""

from code_factory.factory.models import ScorerCards, Scorers, ScorerView, Window


def pass_rate(yes: int, no: int) -> float | None:
    """`yes / (yes + no)`; unclear answers count on neither side; None with no yes or no answer."""
    decided = yes + no
    return yes / decided if decided else None


def scorer_views(cards: ScorerCards) -> Scorers:
    """The provider's cards with `asked` (all three answers) and `pass_rate` added."""
    views = [
        ScorerView(
            repository=card.repository,
            name=card.name,
            question=card.question,
            yes=card.yes,
            no=card.no,
            unclear=card.unclear,
            asked=card.yes + card.no + card.unclear,
            pass_rate=pass_rate(card.yes, card.no),
            average_score=card.average_score,
            window=Window(from_=card.window_since, to=card.window_until),
        )
        for card in cards.cards
    ]
    return Scorers(available=cards.available, cards=views)
