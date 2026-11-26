"""What a checks log says of where its time went, and the lines a run appends to it."""

import re

from code_factory.checks.models import Phases

_MINUTES = re.compile(r"(\d+)m (\d+(?:\.\d+)?)s")
_PLAIN = re.compile(r"(\d+(?:\.\d+)?)s")
_PYTEST = re.compile(r"\bin (\d+(?:\.\d+)?)s \(\d+:\d{2}:\d{2}\)")
_LOCK = " for the heavy-step lock"


def _seconds(text: str) -> float:
    """`12.5s` or `1m 02s` as seconds; 0 for anything else."""
    text = text.strip()
    if found := _MINUTES.fullmatch(text):
        return int(found[1]) * 60 + float(found[2])
    if found := _PLAIN.fullmatch(text):
        return float(found[1])
    return 0.0


def _compiled(line: str) -> float | None:
    rest = line.removeprefix("Finished `test` profile ")
    if rest == line or " in " not in rest:
        return None
    return _seconds(rest.rsplit(" in ", 1)[1])


def _summary(line: str) -> float | None:
    rest = line.removeprefix("Summary [")
    if rest == line or "]" not in rest:
        return None
    return _seconds(rest.split("]", 1)[0])


def _waited(line: str) -> float | None:
    rest = line.removeprefix("gate: ")
    if rest == line or " waited " not in rest:
        return None
    took = rest.split(" waited ", 1)[1]
    return _seconds(took.split(_LOCK, 1)[0]) if _LOCK in took else None


def phases_of(log: str) -> Phases:
    """The compile, test and lock-wait seconds in `log` and the scope the gate chose.

    A log without a part leaves it zero or unset.
    """
    compile_s = tests = wait = 0.0
    scope: str | None = None
    for raw in log.splitlines():
        line = raw.lstrip()
        if (took := _compiled(line)) is not None:
            compile_s += took
        elif (took := _summary(line)) is not None:
            tests += took
        elif (took := _waited(line)) is not None:
            wait += took
        elif line.startswith("gate: rust-test runs "):
            scope = scope or line.removeprefix("gate: rust-test runs ")
        elif found := _PYTEST.search(line):
            tests += float(found[1])
    return Phases(heavy_wait=wait, compile=compile_s, tests=tests, scope=scope)


def phases_line(head: str, wait: float, phases: Phases) -> str:
    """The log line that records the phases of the run of `head`."""
    return (
        f"code-factory checks phases: head {head}, scope {phases.scope or 'none'}, "
        f"wait {wait + phases.heavy_wait:.3f}s, compile {phases.compile:.3f}s, "
        f"tests {phases.tests:.3f}s"
    )


def timing_line(total: float, wait: float, setup: float, command: float) -> str:
    """The log line that records where a run's wall time went."""
    return (
        f"code-factory checks timing: {total:.3f}s total, {wait:.3f}s container and heavy lock, "
        f"{setup:.3f}s setup, {command:.3f}s command and verdict"
    )
