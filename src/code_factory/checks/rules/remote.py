"""How long a runner's claim, offer and decline count, and what a refusal says."""

from datetime import datetime, timedelta
from typing import Literal

CLAIM_HOLDS = timedelta(seconds=60)
OFFER_LIVE = timedelta(seconds=600)
DECLINE_LIVE = timedelta(seconds=86_400)

Refusal = Literal["not_yours", "head_moved", "other_head", "tree_differs"]


def claim_holds(beat_at: datetime, now: datetime) -> bool:
    """Whether a claim last beaten at `beat_at` still holds."""
    return now - beat_at < CLAIM_HOLDS


def offer_live(at: datetime, now: datetime) -> bool:
    """Whether a runner's ask at `at` still counts as an offer."""
    return now - at < OFFER_LIVE


def decline_live(at: datetime, now: datetime) -> bool:
    """Whether a head a runner gave back at `at` is still the board's."""
    return now - at < DECLINE_LIVE


def refusal_sentence(kind: Refusal, subject: str) -> str:
    """What the board answers when it refuses a result."""
    return {
        "not_yours": f"the claim on {subject}'s checks is not yours: claim again",
        "head_moved": (
            f"the pull request's head moved since the claim: {subject}'s result is refused"
        ),
        "other_head": f"the result is for another head than {subject}'s claimed head",
        "tree_differs": (
            f"the tree checked is not the claimed head's tree: {subject}'s result is refused"
        ),
    }[kind]
