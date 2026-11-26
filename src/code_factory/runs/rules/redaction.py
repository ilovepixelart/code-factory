"""Keeping the owner's contexts and a run's keys out of its log.

The board writes the patterns of a run beside its sandbox file; the wrapper, which never touches
the database, applies them to the agent's output chunk by chunk.
"""

import json
from collections.abc import Iterable

from code_factory.agents.service import StartKit
from code_factory.runs.rules.stream import Pattern

KEY_STAND_IN = "[redacted key]"


def redaction_patterns(contexts: Iterable[tuple[str, str]], keys: Iterable[str]) -> list[Pattern]:
    """`(text, stand-in)` for each context as written and as JSON writes it, and each key.

    A JSON body is found both with non-ASCII characters escaped and not, as a runtime may print
    either. An empty text or key has nothing to find.
    """
    patterns: list[Pattern] = []
    for name, text in contexts:
        if not text:
            continue
        stand_in = StartKit.placeholder(name, text)
        patterns.append((text, stand_in))
        for ascii_only in (False, True):
            escaped = json.dumps(text, ensure_ascii=ascii_only)[1:-1]
            if escaped and escaped != text and (escaped, stand_in) not in patterns:
                patterns.append((escaped, stand_in))
    patterns += [(key, KEY_STAND_IN) for key in keys if key]
    return patterns
