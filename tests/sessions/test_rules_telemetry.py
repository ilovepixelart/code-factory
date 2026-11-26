import pytest

from code_factory.sessions.models import Request
from code_factory.sessions.rules import telemetry


def record(name: str, counts: dict[str, object]) -> dict[str, object]:
    return {
        "body": {"stringValue": name},
        "attributes": [{"key": key, "value": value} for key, value in counts.items()],
    }


def export(*records: dict[str, object]) -> dict[str, object]:
    return {"resourceLogs": [{"scopeLogs": [{"logRecords": list(records)}]}]}


def tokens(input_tokens: object, output_tokens: object) -> dict[str, object]:
    return {
        "input_tokens": {"intValue": input_tokens},
        "output_tokens": {"intValue": output_tokens},
    }


def test_an_api_request_reports_its_tokens_as_numbers_or_decimal_strings() -> None:
    body = export(record("claude_code.api_request", tokens(285, "89")))
    assert telemetry.requests(body) == [Request(285, 89)]


def test_other_events_report_nothing_even_with_counts() -> None:
    body = export(record("claude_code.tool_result", tokens(7, 7)))
    assert telemetry.requests(body) == []


@pytest.mark.parametrize(
    "counts",
    [
        {"input_tokens": {"intValue": 5}},
        tokens(-5, 1),
        {"input_tokens": {"doubleValue": 5.5}, "output_tokens": {"intValue": 1}},
        tokens("18446744073709551615", 1),
        tokens(100_000_001, 1),
        tokens("12abc", 1),
        tokens("-3", 1),
        tokens("", 1),
        tokens(True, 1),
        tokens(1.5, 1),
    ],
    ids=[
        "missing",
        "negative",
        "double",
        "huge string",
        "over cap",
        "letters",
        "signed",
        "empty",
        "bool",
        "float",
    ],
)
def test_a_request_with_a_count_missing_negative_fractional_or_over_the_cap_reports_nothing(
    counts: dict[str, object],
) -> None:
    assert telemetry.requests(export(record("claude_code.api_request", counts))) == []


def test_the_cap_itself_and_zero_are_allowed() -> None:
    body = export(record("claude_code.api_request", tokens(100_000_000, 0)))
    assert telemetry.requests(body) == [Request(100_000_000, 0)]


def test_requests_of_every_resource_and_scope_are_read_in_order() -> None:
    first = record("claude_code.api_request", tokens(1, 2))
    second = record("claude_code.api_request", tokens(3, 4))
    body = {
        "resourceLogs": [
            {"scopeLogs": [{"logRecords": [first]}, {"logRecords": [second]}]},
            {"scopeLogs": [{"logRecords": [first]}]},
        ]
    }
    assert telemetry.requests(body) == [Request(1, 2), Request(3, 4), Request(1, 2)]


@pytest.mark.parametrize("body", [{}, [], "x", None, {"resourceLogs": "x"}, {"resourceLogs": [1]}])
def test_a_body_with_no_logs_reports_nothing(body: object) -> None:
    assert telemetry.requests(body) == []


def test_a_decimal_string_past_the_integer_digit_limit_is_refused_not_an_error() -> None:
    assert telemetry.count({"intValue": "0" * 5000 + "5"}) is None


def test_a_decimal_string_of_the_most_digits_is_still_read() -> None:
    assert telemetry.count({"intValue": "0" * 17 + "42"}) == 42
    assert telemetry.count({"intValue": "0" * 18 + "42"}) is None
