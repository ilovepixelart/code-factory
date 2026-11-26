import json

import pytest

from code_factory.sessions.models import Usage
from code_factory.sessions.rules.usage import Totals, summed, transcript_files


def assistant(message_id: str, model: str, tokens: tuple[int, int, int, int]) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "id": message_id,
                "model": model,
                "usage": {
                    "input_tokens": tokens[0],
                    "output_tokens": tokens[1],
                    "cache_read_input_tokens": tokens[2],
                    "cache_creation_input_tokens": tokens[3],
                },
            },
        }
    )


def transcript() -> str:
    """Message a streamed twice (the later counts), b once, a synthetic one and a cost report."""
    cost = {"type": "cost-state", "totalCostUSD": 1.5, "startTime": 1000, "totalDuration": 5000}
    return (
        "\n".join(
            [
                assistant("a", "m", (10, 20, 300, 40)),
                assistant("a", "m", (11, 25, 300, 40)),
                assistant("b", "m", (1, 2, 3, 4)),
                assistant("c", "<synthetic>", (100, 100, 100, 100)),
                json.dumps(cost),
            ]
        )
        + "\n"
    )


# By hand: input 11 + 1, output 25 + 2, cache read 300 + 3, cache write 40 + 4; the cost 1.5
# reported at (1000 + 5000) ms.
EXPECTED = Usage(12, 27, 303, 44, 1.5, 6.0, False)


def whole(text: str) -> Usage:
    totals = Totals()
    totals.absorb_text(text)
    return totals.usage()


def test_a_transcript_read_at_once_counts_each_message_once() -> None:
    assert whole(transcript()) == EXPECTED


def test_a_transcript_read_in_two_parts_is_the_transcript_read_at_once() -> None:
    data = transcript().encode()
    for cut in range(len(data) + 1):
        try:
            first = data[:cut].decode()
        except UnicodeDecodeError:
            continue  # not a character boundary
        totals = Totals()
        consumed = totals.absorb_text(first)
        totals.absorb_text(data[consumed:].decode())
        assert totals.usage() == EXPECTED, f"cut at byte {cut}"


def test_a_last_line_still_being_written_is_left_for_the_next_read() -> None:
    line = assistant("a", "m", (5, 6, 7, 8))
    totals = Totals()
    consumed = totals.absorb_text(f"{line}\n{line[:-10]}")
    assert consumed == len(line) + 1
    assert totals.usage().input == 5


def test_a_complete_last_line_without_a_line_break_counts_at_once_and_only_once() -> None:
    line = assistant("a", "m", (5, 6, 7, 8))
    totals = Totals()
    assert totals.absorb_text(line) == len(line)
    totals.absorb_text("\n")
    assert (totals.usage().input, totals.usage().cache_write) == (5, 8)


def test_bytes_consumed_are_bytes_not_characters() -> None:
    line = json.dumps({"type": "x", "note": "é漢"}, ensure_ascii=False)
    assert Totals().absorb_text(line + "\n") == len(line.encode()) + 1


def test_a_record_with_odd_counts_reads_as_the_previous_reader_did() -> None:
    odd = json.dumps(
        {
            "type": "assistant",
            "message": {
                "id": "m4",
                "model": "claude",
                "usage": {
                    "input_tokens": "12",
                    "output_tokens": True,
                    "cache_read_input_tokens": 3.5,
                },
            },
        }
    )
    skipped = [
        json.dumps(
            {"type": "assistant", "message": {"model": "claude", "usage": {"input_tokens": 7}}}
        ),
        "not json at all",
        "[1, 2]",
    ]
    assert whole("\n".join([odd, *skipped]) + "\n") == Usage(0, 1, 0, 0)


def test_the_latest_cost_report_wins_and_notes_an_unknown_model_cost() -> None:
    first = {
        "type": "cost-state",
        "totalCostUSD": 1.2,
        "startTime": 1790000000000,
        "totalDuration": 60000,
    }
    last = {
        "type": "cost-state",
        "totalCostUSD": 1.5,
        "startTime": 1790000100000,
        "totalDuration": 1500,
        "hasUnknownModelCost": True,
    }
    found = whole(json.dumps(first) + "\n" + json.dumps(last) + "\n")
    assert (found.cost, found.reported_at, found.cost_incomplete) == (1.5, 1790000101.5, True)


def test_a_cost_given_as_an_integer_is_a_float_and_a_cost_of_text_is_ignored() -> None:
    whole_cost = {"type": "cost-state", "totalCostUSD": 2, "startTime": 1790000500000}
    text_cost = {"type": "cost-state", "totalCostUSD": "9"}
    found = whole(json.dumps(whole_cost) + "\n" + json.dumps(text_cost) + "\n")
    assert (found.cost, found.reported_at) == (2.0, 1790000500.0)


def test_a_transcript_names_its_subagents_in_name_order_and_only_jsonl_files() -> None:
    found = transcript_files(["b.jsonl", "notes.txt", "a.jsonl"], "/t/s-sub.jsonl")
    assert found == ["/t/s-sub.jsonl", "/t/s-sub/subagents/a.jsonl", "/t/s-sub/subagents/b.jsonl"]
    assert transcript_files(["a.jsonl"], "") == []


def test_a_sessions_usage_adds_its_subagents_tokens_and_keeps_its_own_cost() -> None:
    own = Usage(100, 1000, 0, 0, None, None, False)
    sub = Usage(1, 49500, 950000, 0, 9.9, 5.0, True)
    assert summed([own, sub]) == Usage(101, 50500, 950000, 0, None, None, False)
    assert summed([]) == Usage()


@pytest.mark.parametrize("text", ["", "\n", "   "])
def test_nothing_to_read_is_no_usage(text: str) -> None:
    assert whole(text) == Usage()


def test_only_a_newline_ends_a_record_so_a_line_separator_inside_a_string_does_not() -> None:
    record = {
        "type": "assistant",
        "message": {
            "id": "m",
            "content": "one" + "".join(map(chr, (0x2028, 0x2029, 0x85, 0x0B))) + "two",
            "usage": {"input_tokens": 5, "output_tokens": 6},
        },
    }
    line = json.dumps(record, ensure_ascii=False)
    totals = Totals()
    assert totals.absorb_text(line + "\n") == len((line + "\n").encode())
    assert (totals.usage().input, totals.usage().output) == (5, 6)


def test_a_record_ended_by_a_carriage_return_and_a_newline_is_read() -> None:
    first = assistant("a", "m", (1, 2, 3, 4))
    second = assistant("b", "m", (10, 20, 30, 40))
    assert whole(first + "\r\n" + second + "\r\n") == Usage(11, 22, 33, 44)
