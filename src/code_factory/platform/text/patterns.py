"""Name patterns: shell wildcards over a whole name, where `*` and `?` match `/` too."""

import fnmatch


def name_matches(name: str, pattern: str) -> bool:
    """Whether `pattern` matches the whole name, case sensitively on every platform."""
    return fnmatch.fnmatchcase(name, pattern)


def _class_end(pattern: str, opened: int) -> int:
    """The index of the `]` ending the class opened at `opened`, as `fnmatch` reads it, or -1."""
    at = opened + 1
    if pattern[at : at + 1] == "!":
        at += 1
    if pattern[at : at + 1] == "]":
        at += 1
    return pattern.find("]", at)


def is_valid_pattern(pattern: str) -> bool:
    """Whether a pattern is not blank and holds no `[` that `fnmatch` would take as a literal.

    A mistyped class would otherwise match nothing and say nothing.
    """
    if not pattern.strip():
        return False
    at = pattern.find("[")
    while at != -1:
        end = _class_end(pattern, at)
        if end == -1:
            return False
        at = pattern.find("[", end + 1)
    return True
