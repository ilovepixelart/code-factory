"""The audit export's line for one activity record."""

import json
from typing import Any

from code_factory.platform.text import masked, stamp
from code_factory.tickets.models import Activity


def _shown(value: object) -> Any:  # noqa: ANN401  # JSON of any shape
    if isinstance(value, str):
        return masked(value)
    text = masked(json.dumps(value))
    try:
        return json.loads(text)
    except ValueError:
        return value


def export_line(record: Activity, repository: str, since: str) -> dict[str, Any] | None:
    """The record as `{at, repository, ticket, kind, by, detail}`, or `None` to leave it out.

    Left out when it has no author or happened before the day `since` (`YYYY-MM-DD`, UTC).
    `detail` is the record's other fields, a secret masked as logs are.
    """
    at = stamp(record.at)
    if not record.by or at[:10] < since:
        return None
    return {
        "at": at,
        "repository": repository,
        "ticket": record.ticket_id,
        "kind": record.kind,
        "by": record.by,
        "detail": {key: _shown(value) for key, value in record.data.items()},
    }
