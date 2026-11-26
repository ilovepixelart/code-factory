"""Secret masking for logs and records: the value after a secret key becomes `[redacted]`."""

import re

REDACTED = "[redacted]"

# A key's quotes may be escaped to any depth, as in a JSON log line embedded in a JSON string.
_KEY_END = r"""\\*["']?\s*[=:]\s*"""
# A value opened by a quote runs to its closing quote: a plain quote's value takes escape
# sequences. An escaped quote opens at a run of backslashes and closes at a run of the same length
# followed by a quote; a run of another length is a quote inside the value (a JSON string embedded
# in another one writes a literal quote with more backslashes). Possessive runs keep the match
# linear. One alternative per opening delimiter keeps the groups the mask retains.
_QUOTED_VALUE = (
    r"""(")(?:[^"\\]|\\.)+"""
    r"""|(?P<esc>\\+")(?:[^"\\]|\\++(?!")|(?!(?P=esc))\\++")+"""
    r"""|(')(?:[^'\\]|\\.)+"""
)
_AUTH_WORD = r"""(?:[^\s"'\\]|\\+[^\s"'\\])+"""
_BARE_VALUE = r"""(?:[^\s"',;\\]|\\+[^\s"',;\\])+"""

_PATTERNS = (
    re.compile(
        rf"(authorization{_KEY_END})(?:{_QUOTED_VALUE}|{_AUTH_WORD}(?:\s+{_AUTH_WORD})?)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"((?:api[_-]?key|token|secret|password|passwd){_KEY_END})(?:{_QUOTED_VALUE}|{_BARE_VALUE})",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:sk-|ghp_|gho_|xoxb-|xoxp-)[A-Za-z0-9_-]+"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def _mask(found: re.Match[str]) -> str:
    kept = "".join(group for group in found.groups() if group is not None)
    return kept + REDACTED


def masked(text: str) -> str:
    """The text with the value of every secret key and every known key shape replaced.

    The key and every quote that opened the value are kept. Text longer than `INLINE_LIMIT` should
    be masked in a worker thread: the patterns backtrack on hostile input.
    """
    for pattern in _PATTERNS:
        text = pattern.sub(_mask, text)
    return text
