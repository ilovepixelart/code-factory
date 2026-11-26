"""What a runner reports of an ended run, and the limits the board puts on it."""

from pydantic import BaseModel, ConfigDict

from code_factory.runs.models import STAGES

TAIL_BYTES = 64 * 1024
MODEL_BYTES = 200
MOST_COST = 1_000_000
TAIL_LINES = 2_000
LINE_MARK = "runner| "  # no reader of a run's log takes such a line for a runtime's event
_REPORTED_STAGES = tuple(s for s in STAGES if s in {"spec", "build", "review"})


class Report(BaseModel):
    """A runner's report of its ended run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: str
    exit_code: int
    cost: float | None = None
    tokens: int | None = None
    model: str = ""
    log_tail: str = ""


def report_problem(report: Report) -> str | None:
    """Why the board does not take this report; `None` when it does."""
    if report.stage not in _REPORTED_STAGES:
        return f'"{report.stage}" is not a column'
    if len(report.log_tail.encode()) > TAIL_BYTES:
        return f"the log tail holds over {TAIL_BYTES} bytes"
    if len(report.model.encode()) > MODEL_BYTES:
        return f"the model holds over {MODEL_BYTES} bytes"
    if report.cost is not None and not 0 <= report.cost <= MOST_COST:
        return f"the cost is not between 0 and {MOST_COST}"
    return None


def stored_tail(tail: str) -> str:
    """`tail` as the board keeps it: its last lines, no control character but a tab, each marked."""
    lines = tail.splitlines()[-TAIL_LINES:]
    return "".join(
        LINE_MARK + "".join(c for c in line if c == "\t" or c.isprintable()) + "\n"
        for line in lines
    )
