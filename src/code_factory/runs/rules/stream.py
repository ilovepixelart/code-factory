"""A stream of a run's output with patterns replaced; imports the standard library only.

The run wrapper imports it, and the wrapper starts with the board down and no framework loaded.
"""

import re
from collections.abc import Sequence

Pattern = tuple[str, str]


class OutputRedaction:
    """A stream being redacted: it holds back the bytes that could still start a pattern.

    A match is written only once it starts before the last `longest - 1` bytes, so every pattern
    that could begin there lies whole inside what is read and the longest one wins.
    """

    def __init__(self, patterns: Sequence[Pattern]) -> None:
        stand_ins: dict[bytes, bytes] = {}
        for found, stand_in in sorted(patterns, key=lambda pair: (-len(pair[0]), pair[0])):
            stand_ins.setdefault(found.encode(), stand_in.encode())
        self._stand_ins = stand_ins
        self._longest = max((len(found) for found in stand_ins), default=0)
        self._regex = (
            re.compile(b"|".join(re.escape(found) for found in stand_ins)) if stand_ins else None
        )
        self._held = b""

    def push(self, chunk: bytes) -> bytes:
        """What can be written of the stream once `chunk` arrived."""
        if self._regex is None:
            return chunk
        data = self._held + chunk
        safe = len(data) - (self._longest - 1)
        out: list[bytes] = []
        at = 0
        for match in self._regex.finditer(data):
            if match.start() >= safe:
                break
            out += [data[at : match.start()], self._stand_ins[match.group()]]
            at = match.end()
        cut = max(at, safe, 0)
        out.append(data[at:cut])
        self._held = data[cut:]
        return b"".join(out)

    def finish(self) -> bytes:
        """The rest of the stream, once it ended."""
        rest, self._held = self._held, b""
        return rest if self._regex is None else self._regex.sub(self._stand_in_of, rest)

    def _stand_in_of(self, match: re.Match[bytes]) -> bytes:
        return self._stand_ins[match.group()]
