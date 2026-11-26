"""The Archive page's rows: the golden cases, then the rules the golden does not reach."""

import json
from pathlib import Path
from typing import Any

import pytest

from code_factory.board.models import ArchiveQuery, OffBoardRow
from code_factory.board.rules.archive import archive_rows as _archive_rows
from code_factory.platform.text.paging import Paging


def archive_rows(  # noqa: PLR0913, PLR0917  # mirrors the six parts of the page query
    rows: list[OffBoardRow],
    q: str,
    sort: str,
    direction: str,
    show: str,
    paging: Paging | None,
) -> dict[str, Any]:
    ask = ArchiveQuery(q=q, sort=sort, dir=direction, show=show, paging=paging)
    return _archive_rows(rows, ask)


GOLDEN = json.loads(
    (Path(__file__).parents[2] / "support/golden/formats/api/archive.golden.json").read_text()
)


def row(ticket_id: str, **more: Any) -> OffBoardRow:  # noqa: ANN401
    values: dict[str, Any] = {
        "repository": "sample",
        "id": ticket_id,
        "title": f"Title {ticket_id}",
        "type": "feature",
        "stage": "spec",
        "archived": True,
    }
    return OffBoardRow(**(values | more))


SAMPLE = [
    row(
        "CF-5",
        title="Released already",
        stage="released",
        archived=False,
        archived_at=1790001000.0,
        release="0.1.0",
    ),
    row("CF-4", title="Archived"),
]


@pytest.mark.parametrize("case", GOLDEN, ids=lambda case: f"q={case['q']!r} sort={case['sort']!r}")
def test_the_golden_cases(case: dict[str, Any]) -> None:
    answer = archive_rows(SAMPLE, case["q"], case["sort"], case["dir"], "", None)
    assert answer["rows"] == case["rows"]
    assert (answer["archived_count"], answer["sort"], answer["dir"]) == (
        case["archived_count"],
        case["sort"] or "archived",
        case["dir"] or "desc",
    )


def ids(answer: dict[str, Any]) -> list[str]:
    return [r["id"] for r in answer["rows"]]


def test_a_ticket_still_on_the_board_is_not_a_row() -> None:
    on_board = row("CF-9", archived=False)
    assert archive_rows([on_board], "", "", "", "", None)["rows"] == []
    assert archive_rows([on_board], "", "", "", "", None)["archived_count"] == 0


def test_the_default_order_is_newest_first() -> None:
    rows = [
        row("CF-1", archived_at=1.0),
        row("CF-2", archived_at=3.0),
        row("CF-3", archived_at=2.0),
    ]
    assert ids(archive_rows(rows, "", "", "", "", None)) == ["CF-2", "CF-3", "CF-1"]


def test_an_unknown_sort_falls_back_to_newest_first_whatever_the_direction() -> None:
    rows = [row("CF-1", archived_at=1.0), row("CF-2", archived_at=3.0)]
    answer = archive_rows(rows, "", "colour", "asc", "", None)
    assert (ids(answer), answer["sort"], answer["dir"]) == (["CF-2", "CF-1"], "archived", "desc")


def test_equal_sort_values_keep_the_board_order() -> None:
    rows = [row("CF-10", rank=0), row("CF-2", rank=0), row("CF-7", rank=1)]
    assert ids(archive_rows(rows, "", "type", "asc", "", None)) == ["CF-7", "CF-2", "CF-10"]


def test_priority_sorts_urgent_to_low_then_unknown() -> None:
    rows = [
        row("CF-1", priority="low"),
        row("CF-2", priority=""),
        row("CF-3", priority="urgent"),
        row("CF-4", priority="high"),
    ]
    assert ids(archive_rows(rows, "", "priority", "asc", "", None)) == [
        "CF-3",
        "CF-4",
        "CF-1",
        "CF-2",
    ]


def test_title_and_assignee_sort_without_regard_to_case() -> None:
    rows = [row("CF-1", title="B"), row("CF-2", title="a")]
    assert ids(archive_rows(rows, "", "title", "asc", "", None)) == ["CF-2", "CF-1"]
    people = [row("CF-1", assignee="Bea"), row("CF-2", assignee="al")]
    assert ids(archive_rows(people, "", "assignee", "asc", "", None)) == ["CF-2", "CF-1"]


def test_stage_sorts_by_column_index() -> None:
    rows = [
        row("CF-1", stage="released", archived=False),
        row("CF-2", stage="build"),
        row("CF-3", stage="spec"),
    ]
    assert ids(archive_rows(rows, "", "stage", "asc", "", None)) == ["CF-3", "CF-2", "CF-1"]


def test_id_sorts_naturally_and_desc_reverses() -> None:
    rows = [row("CF-10"), row("CF-2")]
    assert ids(archive_rows(rows, "", "id", "asc", "", None)) == ["CF-2", "CF-10"]
    assert ids(archive_rows(rows, "", "id", "desc", "", None)) == ["CF-10", "CF-2"]


def test_the_query_is_trimmed_lower_case_and_matches_id_or_title() -> None:
    rows = [row("CF-1", title="Fix LOGIN"), row("CF-2", title="Other")]
    assert ids(archive_rows(rows, "  login ", "id", "asc", "", None)) == ["CF-1"]
    assert ids(archive_rows(rows, "cf-2", "id", "asc", "", None)) == ["CF-2"]


def test_show_released_and_show_hand_each_keep_one_kind() -> None:
    assert ids(archive_rows(SAMPLE, "", "id", "asc", "released", None)) == ["CF-5"]
    assert ids(archive_rows(SAMPLE, "", "id", "asc", "hand", None)) == ["CF-4"]
    assert ids(archive_rows(SAMPLE, "", "id", "asc", "anything", None)) == ["CF-4", "CF-5"]


def test_a_released_ticket_archived_by_hand_is_released_not_hand() -> None:
    both = [row("CF-1", stage="released", archived=True)]
    assert ids(archive_rows(both, "", "id", "asc", "hand", None)) == []


def test_the_count_ignores_show_and_the_query() -> None:
    assert archive_rows(SAMPLE, "zzz", "id", "asc", "released", None)["archived_count"] == 2


def test_a_page_carries_its_total_and_position() -> None:
    rows = [row(f"CF-{n}") for n in range(1, 6)]
    answer = archive_rows(rows, "", "id", "asc", "", Paging(2, 2))
    assert ids(answer) == ["CF-3", "CF-4"]
    assert (answer["total"], answer["page"], answer["size"]) == (5, 2, 2)


def test_a_page_past_the_last_is_the_last_and_an_empty_list_is_page_one() -> None:
    rows = [row(f"CF-{n}") for n in range(1, 4)]
    last = archive_rows(rows, "", "id", "asc", "", Paging(9, 2))
    assert (ids(last), last["page"]) == (["CF-3"], 2)
    empty = archive_rows([], "", "id", "asc", "", Paging(5, 2))
    assert (empty["rows"], empty["total"], empty["page"]) == ([], 0, 1)


def test_an_unpaged_answer_has_no_page_keys() -> None:
    assert {"total", "page", "size"} & set(archive_rows(SAMPLE, "", "", "", "", None)) == set()
