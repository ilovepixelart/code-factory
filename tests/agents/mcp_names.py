"""The names of the board's tools as the run-build golden lists them: what a prompt may name."""

import json
import re
from collections.abc import Collection
from pathlib import Path

GOLDEN = Path(__file__).parent.parent / "golden" / "mcp" / "tools.run-build.json"
TOOLS: set[str] = {str(tool["name"]) for tool in json.loads(GOLDEN.read_text(encoding="utf-8"))}


def tools_named(text: str, available: Collection[str] = TOOLS) -> set[str]:
    """The backticked snake_case words of `text` that are tool names."""
    return {word for word in re.findall(r"`([a-z]+(?:_[a-z]+)+)`", text) if word in available}


def unknown_tools(text: str, known_words: set[str], available: Collection[str] = TOOLS) -> set[str]:
    """The backticked snake_case words of `text` that are neither tools nor `known_words`."""
    words: set[str] = set(re.findall(r"`([a-z]+(?:_[a-z]+)+)`", text))
    return words.difference(available, known_words)
