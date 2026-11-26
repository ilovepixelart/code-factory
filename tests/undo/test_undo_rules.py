"""The undo window: 30 seconds to take a change back, and the housekeeping margin after it.

The values are the ticket-writes spec's: an entry is live while `now <= expires_at` (exactly 30 s
live, 30 s plus 1 ms gone) and a sweep deletes entries expired for more than 60 s.
"""

from datetime import UTC, datetime, timedelta

from code_factory.undo.rules import expires_at, new_token, sweep_cutoff, undo_live

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def test_an_entry_offered_now_expires_thirty_seconds_later() -> None:
    assert expires_at(NOW) == datetime(2026, 11, 23, 12, 0, 30, tzinfo=UTC)


def test_an_entry_is_live_at_exactly_thirty_seconds() -> None:
    assert undo_live(expires_at(NOW), NOW + timedelta(seconds=30)) is True


def test_an_entry_is_gone_one_millisecond_after_thirty_seconds() -> None:
    assert undo_live(expires_at(NOW), NOW + timedelta(seconds=30, milliseconds=1)) is False


def test_a_sweep_keeps_what_expired_within_the_last_minute() -> None:
    assert sweep_cutoff(NOW) == datetime(2026, 11, 23, 11, 59, tzinfo=UTC)


def test_a_token_is_32_lowercase_hex_characters_and_never_repeats() -> None:
    tokens = {new_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) == 32 and set(t) <= set("0123456789abcdef") for t in tokens)
