"""The board's public API: `BoardService`, the sources it reads and the ports others answer.

The runs, checks, delivery, follower, metrics and ticket-writes modules register an adapter under
each port's class in their own `provide`; `board.module.board_sources` reads them from the registry.
"""

from code_factory.board.ports import (
    CardChecks,
    CardDelivery,
    CardQueue,
    CardRuns,
    ColumnLimits,
    MergeLedger,
)
from code_factory.board.service.board import BoardService
from code_factory.board.service.sources import BoardSources

__all__ = [
    "BoardService",
    "BoardSources",
    "CardChecks",
    "CardDelivery",
    "CardQueue",
    "CardRuns",
    "ColumnLimits",
    "MergeLedger",
]
