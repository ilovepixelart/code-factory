"""Readers of the markdown a ticket document holds: sections, pipe tables and id mentions."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Row:
    """The cells of one table row and its 1-based line in the document."""

    cells: tuple[str, ...]
    line: int


def is_word(char: str) -> bool:
    """A word character: a letter or number of any script, or an underscore."""
    return char.isalnum() or char == "_"


def _digit(char: str) -> bool:
    return len(char) == 1 and "0" <= char <= "9"


def _line_starts(text: str) -> list[int]:
    return [0, *(at + 1 for at, char in enumerate(text) if char == "\n")]


def _section_span(text: str, heading: str) -> tuple[int, int] | None:
    start = 0
    while start <= len(text):
        stop = text.find("\n", start)
        line_end = len(text) if stop == -1 else stop
        if text[start:line_end].rstrip() == heading:
            begin = start + len(heading)
            end = text.find("\n## ", begin)
            return begin, len(text) if end == -1 else end
        if stop == -1:
            break
        start = stop + 1
    return None


def section(text: str, heading: str) -> str | None:
    """The body from the line that is exactly `heading` up to the next `## ` line.

    Lines start after a newline only, so `### Requirements notes` never opens `## Requirements`.
    """
    found = _section_span(text, heading)
    return None if found is None else text[found[0] : found[1]]


def _cells(line: str) -> tuple[str, ...]:
    return tuple(cell.strip() for cell in line.strip().strip("|").split("|"))


def _is_separator(cells: tuple[str, ...]) -> bool:
    return cells[0].strip("-: ") == ""


def section_rows(document: str, heading: str) -> list[Row]:
    """The rows of the pipe tables under a section, header and separator rows left out.

    A header is the row a separator row follows, whatever it says. A separator row is one whose
    first cell holds only `-`, `:` and spaces, so a row with an empty first cell is dropped too.
    """
    found = _section_span(document, heading)
    if found is None:
        return []
    first_line = document.count("\n", 0, found[0]) + 1
    rows = [
        Row(_cells(line), first_line + offset)
        for offset, line in enumerate(document[found[0] : found[1]].split("\n"))
        if line.lstrip().startswith("|")
    ]
    return [
        row
        for index, row in enumerate(rows)
        if not _is_separator(row.cells)
        and not (index + 1 < len(rows) and _is_separator(rows[index + 1].cells))
    ]


def mentions(text: str, ident: str) -> bool:
    """Whether `ident` occurs with no word character or `-` before it and no ASCII digit after."""
    at = text.find(ident)
    while at != -1:
        before = text[at - 1 : at] if at else ""
        after = text[at + len(ident) : at + len(ident) + 1]
        if not (before and (is_word(before) or before == "-")) and not _digit(after):
            return True
        at = text.find(ident, at + 1)
    return False


def line_prefixes(text: str, ident: str) -> bool:
    """Whether some line starts with `ident` not followed by an ASCII digit."""
    for start in _line_starts(text):
        if text.startswith(ident, start):
            after = text[start + len(ident) : start + len(ident) + 1]
            if not _digit(after):
                return True
    return False
