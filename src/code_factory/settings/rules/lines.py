"""Where a key is in a TOML text. `tomllib` keeps no source spans, so these scan for the line.

A key written dotted or in an inline table is not found: the line reads 0, as a problem about the
whole file does.
"""

import re

_HEADER = re.compile(r"(\[\[?)([^\]]*)(\]\]?)\s*(?:#.*)?")


def _header(line: str) -> tuple[bool, str] | None:
    """`(is a list entry, name)` of a `[name]` or `[[name]]` header, a comment after it allowed."""
    found = _HEADER.fullmatch(line)
    if found is None or len(found.group(1)) != len(found.group(3)):
        return None
    return len(found.group(1)) == 2, str(found.group(2)).strip()  # noqa: PLR2004  # `[[`


def _names(line: str, key: str) -> bool:
    name, separator, _ = line.partition("=")
    return bool(separator) and name.strip() == key


def key_line(text: str, table: str, key: str) -> int:
    """The 1-based line of the first `key =` under `[table]`, 0 when there is none."""
    current = ""
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        header = _header(line)
        if header is not None:
            is_entry, name = header
            current = f"[{name}]" if is_entry else name
        elif current == table and _names(line, key):
            return number
    return 0


def header_line(text: str, name: str, index: int = 0) -> int:
    """The line of the `index`th `[name]` or `[[name]]` header, 0 when there is none."""
    seen = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        header = _header(raw.strip())
        if header is not None and header[1] == name:
            if seen == index:
                return number
            seen += 1
    return 0


def entry_line(text: str, name: str, index: int, key: str) -> int:
    """The line of `key` in the `index`th `[[name]]` entry, 0 when there is none."""
    seen = 0
    inside = False
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.startswith("["):
            header = _header(line)
            is_this = header is not None and header == (True, name)
            inside = is_this and seen == index
            seen += is_this
        elif inside and _names(line, key):
            return number
    return 0
