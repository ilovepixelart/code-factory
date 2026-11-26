"""The file that tells the capture hook what owner context to keep out of the spool."""

import json
from collections.abc import Iterable


def redaction_text(patterns: Iterable[tuple[str, str]], references: Iterable[str]) -> str:
    r"""The text of `redaction.json`: the references that may run, and the replacements.

    Each find also stands in its JSON-escaped form, which is how the same text sits inside a
    payload that writes non-ASCII characters as `\u` escapes. The longest find comes first, so a
    context that holds another is replaced whole.
    """
    pairs: dict[str, str] = {}
    for find, replacement in patterns:
        if not find:
            continue
        pairs.setdefault(find, replacement)
        escaped = json.dumps(find)[1:-1]
        if escaped != find:
            pairs.setdefault(escaped, replacement)
    ordered = sorted(pairs.items(), key=lambda pair: (-len(pair[0]), pair[0]))
    return json.dumps({"references": list(references), "patterns": [list(p) for p in ordered]})
