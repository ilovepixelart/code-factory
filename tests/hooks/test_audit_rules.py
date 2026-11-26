"""The audit export's line for one activity record: who did what, when, with secrets masked."""

from datetime import UTC, datetime

from code_factory.hooks.rules.audit import export_line
from code_factory.tickets.models import Activity


def record(at: str, *, by: str = "alex", kind: str = "hold_released", **data: object) -> Activity:
    return Activity(
        id=1,
        ticket_id="CF-1",
        at=datetime.fromisoformat(at).astimezone(UTC),
        kind=kind,
        by=by,
        data=dict(data),
    )


def test_a_record_becomes_a_line_with_the_keys_in_the_documented_order() -> None:
    line = export_line(record("2026-11-02T11:00:00+00:00", commit="abc"), "api", "2026-11-01")

    assert line == {
        "at": "2026-11-02T11:00:00Z",
        "repository": "api",
        "ticket": "CF-1",
        "kind": "hold_released",
        "by": "alex",
        "detail": {"commit": "abc"},
    }
    assert line is not None
    assert list(line) == ["at", "repository", "ticket", "kind", "by", "detail"]


def test_the_day_boundary_includes_the_first_second_and_excludes_the_last_before() -> None:
    assert export_line(record("2026-11-01T00:00:00+00:00"), "api", "2026-11-01") is not None
    assert export_line(record("2026-10-31T23:59:59+00:00"), "api", "2026-11-01") is None


def test_a_record_with_no_author_is_skipped() -> None:
    assert export_line(record("2026-11-02T00:00:00+00:00", by=""), "api", "2026-11-01") is None


def test_a_secret_in_a_text_detail_is_masked() -> None:
    line = export_line(
        record("2026-11-02T00:00:00+00:00", note="token ghp_secret123 leaked"), "api", "2026-11-01"
    )

    assert line is not None
    assert "ghp_secret123" not in str(line)
    assert line["detail"] == {"note": "token [redacted] leaked"}


def test_a_secret_inside_a_nested_value_is_masked_and_the_value_keeps_its_shape() -> None:
    line = export_line(
        record(
            "2026-11-02T00:00:00+00:00",
            steps=[{"env": "sk-abcdef123456"}, 3],
            count=7,
            ok=True,
        ),
        "api",
        "2026-11-01",
    )

    assert line is not None
    assert line["detail"] == {"steps": [{"env": "[redacted]"}, 3], "count": 7, "ok": True}


def test_a_detail_with_no_data_is_an_empty_object() -> None:
    line = export_line(record("2026-11-02T00:00:00+00:00"), "api", "2026-11-01")

    assert line is not None
    assert line["detail"] == {}
