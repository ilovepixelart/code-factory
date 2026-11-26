"""Step times, the `times` report, throughput, forecast and yields through the service."""

from code_factory.metrics.models import StageMove
from code_factory.metrics.service import MetricsService
from git_log_values import SHIPPED
from metrics_support import when


def test_other_modules_read_when_a_ticket_reached_review_from_its_moves() -> None:
    moves = [
        StageMove(at=when(10.0), to="build"),
        StageMove(at=when(20.0), to="review"),
        StageMove(at=when(30.0), to="merged"),
    ]
    assert MetricsService.reached_done(moves) == when(20.0)
    assert MetricsService.reached_done(moves[:1]) is None


def test_other_modules_parse_a_merge_log() -> None:
    assert [m.pull for m in MetricsService.merges_in_log(SHIPPED)] == [9, 7]
    assert [m.pull for m in MetricsService.merges_in_log(SHIPPED, 1600.0)] == [9]
