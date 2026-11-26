"""Ranking documents by a query: BM25 over whole words, best first."""

import math
import re
from collections import Counter
from collections.abc import Sequence

from code_factory.memory_extras.models import Doc

K1 = 1.2
B = 0.75
# A word held by most documents would score at or below zero; SQLite's FTS5 floors it too.
MIN_IDF = 1e-6
_TOKEN = re.compile(r"[^\W_]+")


def words_of(text: str) -> list[str]:
    """The lowercase alphanumeric runs of the text, in order."""
    return [word.lower() for word in _TOKEN.findall(text)]


def _idf(total: int, held: int) -> float:
    return max(math.log((total - held + 0.5) / (held + 0.5)), MIN_IDF)


def scores(docs: Sequence[Doc], words: Sequence[str]) -> list[tuple[Doc, float]]:
    """The documents holding every word with their BM25 score, in the order given.

    The corpus is `docs`: a word's idf counts the documents of `docs` that hold it.
    """
    counted = [Counter(words_of(doc.text)) for doc in docs]
    lengths = [sum(count.values()) for count in counted]
    average = sum(lengths) / len(docs) if docs else 0.0
    held = {word: sum(1 for count in counted if count[word]) for word in set(words)}
    found = []
    for doc, count, length in zip(docs, counted, lengths, strict=True):
        if not words or not all(count[word] for word in words):
            continue
        norm = K1 * (1 - B + B * length / average)
        score = sum(
            _idf(len(docs), held[word]) * count[word] * (K1 + 1) / (count[word] + norm)
            for word in words
        )
        found.append((doc, score))
    return found


def rank(docs: Sequence[Doc], words: Sequence[str]) -> list[Doc]:
    """The documents holding every word, best first, ties by path."""
    ordered = sorted(scores(docs, words), key=lambda found: (-found[1], found[0].path))
    return [doc for doc, _ in ordered]
