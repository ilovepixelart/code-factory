"""A production error report: its fields, and the release a new report follows."""

from code_factory.hooks.models import ReleaseFact, ReportFields, Tie
from code_factory.platform.text import masked, shown

REFUSED = "a report needs a one-line fingerprint"
DEFAULT_WATCH_DAYS = 7
FIELD_LIMIT = 2_000
DAY_SECONDS = 86_400
LINE_BREAKS = frozenset("\n\r\x0b\x0c\x1c\x1d\x1e\x85") | {chr(0x2028), chr(0x2029)}


def _scalar(value: object) -> str:
    """JSON text of a string, number or boolean; empty for null, a list or an object."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value) if isinstance(value, str | int | float) else ""


def _field(report: dict[str, object], name: str) -> str:
    text = _scalar(report.get(name))
    # Outside text: what shows as nothing could spell words its sender never saw.
    return masked(shown(text)[0].strip())[:FIELD_LIMIT]


def has_line_break(text: str) -> bool:
    """Whether the text holds a character that ends a line."""
    return any(char in LINE_BREAKS for char in text)


def normalise(report: object) -> ReportFields | str:
    """The report's fields, or the sentence refusing it.

    The ticket is stored and shown, so a secret in a message is masked and a field is cut.
    """
    fields = report if isinstance(report, dict) else {}
    fingerprint = _field(fields, "fingerprint")
    if not fingerprint or has_line_break(fingerprint):
        return REFUSED
    return ReportFields(
        fingerprint=fingerprint,
        title=_field(fields, "title"),
        message=_field(fields, "message"),
        release=_field(fields, "release"),
    )


def release_tie(releases: list[ReleaseFact], named: str, now: float, watch_days: int) -> Tie | None:
    """The release a new report follows, `releases` oldest first.

    The one `named` when it exists, else the newest while it shipped at most `watch_days` days
    ago (`watch_days` of 0 closes the window). `None` when the release shipped no tickets.
    """
    named = "" if has_line_break(named) else named
    release = next((r for r in releases if named and r.version == named), None)
    said = "Reported against release"
    if release is None:
        newest = releases[-1] if releases else None
        if newest is None or watch_days <= 0 or now - newest.at > watch_days * DAY_SECONDS:
            return None
        release, said = newest, "Seen within the verification window of release"
    if not release.tickets:
        return None
    ids = ", ".join(release.tickets)
    return Tie(
        caused_by=list(release.tickets), paragraph=f"{said} {release.version}, which shipped {ids}."
    )
