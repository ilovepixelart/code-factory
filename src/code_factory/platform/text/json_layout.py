"""The byte layout of the JSON the board writes: three styles, ASCII only, no trailing newline."""

import json
from enum import StrEnum


class Style(StrEnum):
    """How a JSON value is laid out."""

    DEFAULT = "default"
    COMPACT = "compact"
    INDENT2 = "indent2"


def render(value: object, style: Style = Style.DEFAULT) -> str:
    """The value as JSON text in a style, with every non-ASCII character escaped.

    Keys keep their insertion order, floats are written in their shortest round-trip form and
    `NaN` and the infinities are written as such. The caller adds a final newline when it wants one.
    """
    match style:
        case Style.COMPACT:
            return json.dumps(value, separators=(",", ":"))
        case Style.INDENT2:
            return json.dumps(value, indent=2)
        case Style.DEFAULT:
            return json.dumps(value)
