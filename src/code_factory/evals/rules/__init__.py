"""Pure rules of evals: task sets, scores, comparison and scorers."""

from code_factory.evals.rules.scorers import (
    asked_of,
    counts,
    due,
    firing_body,
    firing_title,
    parse_answer,
    pass_rate,
    scorers_of,
)
from code_factory.evals.rules.scoring import compare, pick_pair, report_lines, scores, setup_name
from code_factory.evals.rules.tasksets import (
    BUILD_HEADER,
    append_text,
    escape_block,
    parse_task_set,
    set_name_ok,
    task_block,
    toml_string,
)

__all__ = [
    "BUILD_HEADER",
    "append_text",
    "asked_of",
    "compare",
    "counts",
    "due",
    "escape_block",
    "firing_body",
    "firing_title",
    "parse_answer",
    "parse_task_set",
    "pass_rate",
    "pick_pair",
    "report_lines",
    "scorers_of",
    "scores",
    "set_name_ok",
    "setup_name",
    "task_block",
    "toml_string",
]
