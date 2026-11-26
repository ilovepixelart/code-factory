"""How many tool calls one caller may make a minute: the MCP specification has servers limit them.

A sliding window per token, in memory: a burst a model may make while working passes, a loop
calling without end is stopped. Each listener process counts its own calls.
"""

import time
from collections import deque
from collections.abc import Callable

CALLS_PER_MINUTE = 120
WINDOW_S = 60.0


class CallRate:
    """Admits at most `per_minute` calls per key in any 60 seconds."""

    def __init__(
        self, per_minute: int = CALLS_PER_MINUTE, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._calls: dict[str, deque[float]] = {}

    def wait(self, key: str) -> float | None:
        """Admit a call by `key`: `None`, or the seconds until the window has room again."""
        now = self._clock()
        calls = self._calls.setdefault(key, deque())
        while calls and now - calls[0] >= WINDOW_S:
            calls.popleft()
        if len(calls) >= self._per_minute:
            return WINDOW_S - (now - calls[0])
        calls.append(now)
        return None

    def refusal(self, waited: float) -> str:
        """What a caller over the limit is told."""
        return (
            f"rate limited: {self._per_minute} tool calls in the last minute. "
            f"Wait {max(1, round(waited))} s, then call again."
        )
