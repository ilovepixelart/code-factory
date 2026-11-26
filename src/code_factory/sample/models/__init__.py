"""What a sample holds: plain data, loaded by `service`. `board.py` and `demo.py` hold one each."""

from code_factory.sample.models.board import (
    BOARD_DOCUMENTS,
    BOARD_MEMORY,
    BOARD_TICKETS,
    LONG_DESCRIPTION,
    OWNER_ENTROPY,
)

SAMPLE_NAMES = ("empty", "board", "demo")

__all__ = [
    "BOARD_DOCUMENTS",
    "BOARD_MEMORY",
    "BOARD_TICKETS",
    "LONG_DESCRIPTION",
    "OWNER_ENTROPY",
    "SAMPLE_NAMES",
]
