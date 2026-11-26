"""The talk on a ticket as the page's activity lines."""

from code_factory.talk.models import TalkEntry
from code_factory.tickets.models import ActivityEntry

_SPEAKERS = {"owner": "You", "run": "An agent"}

_SENTENCES = {
    "question": "{by} asked",
    "answer": "{by} answered",
    "comment": "{by} commented",
    "message": "{by} sent a message",
}


def _speaker(by: str) -> str:
    """The author of `by` (`owner:<label>`, `run:<id>`) in words that start a sentence."""
    if not by:
        return "Someone"
    named = _SPEAKERS.get(by.partition(":")[0])
    return named if named is not None else by[:1].upper() + by[1:]


def talk_line(record: TalkEntry) -> ActivityEntry:
    """A question, answer, comment or message as an activity line of the `talk` source."""
    return ActivityEntry(
        at=record.at,
        kind=record.kind,
        by=record.by,
        sentence=_SENTENCES[record.kind].format(by=_speaker(record.by)),
        data={"text": record.text},
        source="talk",
    )
