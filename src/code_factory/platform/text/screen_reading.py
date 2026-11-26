"""Text as a reader takes it in: invisible characters gone, lookalikes plain, phrases found."""

import html
import re
import unicodedata
from bisect import bisect_right
from collections.abc import Iterator

# Characters that show as nothing (Unicode's default ignorable code points and format controls,
# tag characters included), which would split a phrase a reader, or a model, still reads whole.
_INVISIBLE = (
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
    (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164),
    (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF),
)  # fmt: skip

# Letters of other scripts drawn like Latin ones, read as the Latin letter.
_LOOKALIKES = str.maketrans(
    {
        0x0430: "a", 0x0435: "e", 0x043E: "o", 0x0440: "p", 0x0441: "c", 0x0445: "x",
        0x0443: "y", 0x0456: "i", 0x0458: "j", 0x0455: "s", 0x0501: "d", 0x04BB: "h",
        0x0261: "g", 0x03BF: "o", 0x03B1: "a", 0x03B5: "e", 0x03B9: "i", 0x03BD: "v",
        0x03C1: "p", 0x0131: "i", 0x0491: "r", 0x0578: "n",
    }
)  # fmt: skip

# Phrases that address an agent reading the text rather than a person.
INSTRUCTIONS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore the above instructions",
    "ignore your instructions",
    "disregard previous instructions",
    "disregard all previous instructions",
    "forget your instructions",
    "<|im_start|>",
    "[inst]",
)
_EMPHASIS = str.maketrans("", "", "*_~`")
# What Markdown renders away: HTML comments and tags (a `<` before a letter or `/`, so the
# `<|im_start|>` phrase is not one), which may span lines.
_TAGS = re.compile(r"<!--.*?-->|</?[A-Za-z][^>]*>", re.DOTALL)
# What a renderer decodes: a backslash before punctuation and a character entity.
_DECODED = re.compile(
    r"\\([!-/:-@\[-`{-~])|&(?:#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});"
)


def numbered(text: str) -> Iterator[tuple[int, str]]:
    """The lines of a text as a forge numbers them, from 1.

    Split on a newline only (not `splitlines`, which breaks at more characters), one trailing
    empty line dropped and each trailing carriage return removed.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for number, line in enumerate(lines, start=1):
        yield number, line.removesuffix("\r")


def _decoded(found: re.Match[str]) -> str:
    return str(found.group(1) or html.unescape(found.group(0)))


def _without_markup(text: str) -> str:
    """The text without its HTML comments and tags, their line breaks kept."""
    return _TAGS.sub(lambda found: "\n" * found.group(0).count("\n"), text)


def _invisible(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in _INVISIBLE)


def shown(text: str) -> tuple[str, int]:
    """The text without the characters that show as nothing, and how many it held."""
    kept = "".join(char for char in text if not _invisible(char))
    return kept, len(text) - len(kept)


def plain_words(line: str) -> str:
    """A line as a reader takes it in.

    Without invisible characters, in compatibility form (fullwidth and styled letters as plain
    ones, entities and backslash escapes decoded), lowercased per character (`str.lower` of a
    whole string is context sensitive), other scripts' lookalike letters as Latin, and without the
    marks Markdown reads as emphasis.
    """
    folded = unicodedata.normalize("NFKC", shown(_DECODED.sub(_decoded, line))[0])
    lowered = "".join(char.lower() for char in folded)
    return lowered.translate(_LOOKALIKES).translate(_EMPHASIS)


def _joined(text: str) -> tuple[str, list[tuple[int, int]]]:
    """The words of the whole text single-spaced, with where each starts and on which line."""
    pieces: list[str] = []
    starts: list[tuple[int, int]] = []
    length = 0
    for number, line in numbered(_without_markup(text)):
        for word in plain_words(line).split():
            if pieces:
                length += 1
            starts.append((length, number))
            pieces.append(word)
            length += len(word)
    return " ".join(pieces), starts


def instruction_lines(text: str) -> list[int]:
    """The lines where an instruction aimed at an agent starts, in order, once each.

    A phrase's words are found in a row however the text splits them over lines, hides characters
    in them, draws their letters or marks them for emphasis.
    """
    joined, starts = _joined(text)
    offsets = [start for start, _ in starts]
    found: set[int] = set()
    for phrase in INSTRUCTIONS:
        needle = plain_words(phrase)
        at = joined.find(needle)
        while at != -1:
            found.add(starts[bisect_right(offsets, at) - 1][1])
            at = joined.find(needle, at + 1)
    return sorted(found)
