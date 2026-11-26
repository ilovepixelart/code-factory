"""The Archive page: tickets off the board, searched, sorted and paged."""

from collections.abc import Callable
from typing import Any

from code_factory.board.models import ArchiveQuery, OffBoardRow
from code_factory.board.rules.columns import COLUMNS
from code_factory.board.rules.order import natural_key, rank_key
from code_factory.platform.text.paging import page_of

PRIORITIES = ("urgent", "high", "medium", "low")
STAGES = (*COLUMNS, "released")
RELEASED = "released"
DEFAULT_SORT = ("archived", "desc")

_SORT_KEYS: dict[str, Callable[[OffBoardRow], Any]] = {
    "id": lambda row: natural_key(row.id),
    "title": lambda row: row.title.lower(),
    "type": lambda row: row.type,
    "stage": lambda row: STAGES.index(row.stage) if row.stage in STAGES else len(STAGES),
    "priority": lambda row: (
        PRIORITIES.index(row.priority) if row.priority in PRIORITIES else len(PRIORITIES)
    ),
    "assignee": lambda row: row.assignee.lower(),
    "repository": lambda row: row.repository,
    "archived": lambda row: row.archived_at,
}


def _shown(row: OffBoardRow, show: str) -> bool:
    match show:
        case "released":
            return row.stage == RELEASED
        case "hand":
            return row.archived and row.stage != RELEASED
        case _:
            return True


def _as_answered(row: OffBoardRow) -> dict[str, Any]:
    return {
        "repository": row.repository,
        "id": row.id,
        "title": row.title,
        "type": row.type,
        "stage": row.stage,
        "archived": row.archived,
        "archived_at": row.archived_at,
        "release": row.release,
    }


def archive_rows(rows: list[OffBoardRow], ask: ArchiveQuery) -> dict[str, Any]:
    """What the Archive page shows: rows off the board that match `query`, in the asked order.

    The base order is the board's (column, then rank, then id), so equal sort values keep it; the
    default is newest first. `archived_count` counts both kinds before `show` and `query` apply.
    """
    base = sorted(
        (row for row in rows if row.archived or row.stage == RELEASED),
        key=lambda row: (_SORT_KEYS["stage"](row), rank_key(row.rank, row.id)),
    )
    needle = ask.q.strip().lower()
    found = [
        row
        for row in base
        if _shown(row, ask.show) and (needle in row.id.lower() or needle in row.title.lower())
    ]
    key, order = (ask.sort, ask.dir) if ask.sort in _SORT_KEYS else DEFAULT_SORT
    found.sort(key=_SORT_KEYS[key], reverse=order == "desc")
    answer: dict[str, Any] = {"sort": key, "dir": order, "archived_count": len(base)}
    if ask.paging is None:
        return answer | {"rows": [_as_answered(row) for row in found]}
    return page_of(found, ask.paging).map(_as_answered).into_answer(answer, "rows")
