"""A new entry may not say what the repository's CLAUDE.md already says."""

import re

MIN_WORDS = 4
_WORDS = re.compile(r"[^\W_]+")
_SENTENCES = re.compile(r"(?<=\. )")


def _words(text: str) -> list[str]:
    return [word.lower() for word in _WORDS.findall(text)]


def _blocks(claude_md: str) -> list[tuple[int, str]]:
    """The file as a reader takes it: a bullet or paragraph wrapped over lines is one block."""
    blocks: list[tuple[int, str]] = []
    opened = False
    for number, raw in enumerate(claude_md.splitlines(), start=1):
        text = raw.strip()
        item = text.startswith(("- ", "* "))
        if not text or text.startswith("#"):
            opened = False
        elif opened and not item:
            first, joined = blocks[-1]
            blocks[-1] = (first, f"{joined} {text}")
        else:
            blocks.append((number, text.lstrip("-*").strip()))
            opened = True
    return blocks


def _lines(claude_md: str) -> list[tuple[int, str]]:
    return [
        (number, sentence.strip())
        for number, block in _blocks(claude_md)
        for sentence in _SENTENCES.split(block)
    ]


def _holds(long: list[str], short: list[str]) -> bool:
    size = len(short)
    return size >= MIN_WORDS and any(
        long[at : at + size] == short for at in range(len(long) - size + 1)
    )


def restated(statement: str, claude_md: str) -> tuple[int, str] | None:
    """The CLAUDE.md line, with its number, that `statement` restates; None when no line does.

    One of the two holds the other as a run of words, case and punctuation ignored, and the
    shorter has at least four words.
    """
    said = _words(statement)
    for number, line in _lines(claude_md):
        theirs = _words(line)
        short, long = (said, theirs) if len(said) <= len(theirs) else (theirs, said)
        if _holds(long, short):
            return number, line
    return None
