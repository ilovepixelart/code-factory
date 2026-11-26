"""Scores of suite runs, the report lines and the comparison of two setups."""

import shlex
from collections.abc import Mapping, Sequence
from pathlib import PurePath

from code_factory.evals.models import Comparison, EvalRecord, Kind, Role, Setup


def scores(passes: Mapping[str, Sequence[bool]]) -> tuple[float, float, float]:
    """(pass@1, pass^k, pass@k) over tasks: mean share passed, all passed, some passed."""
    runs = [list(p) for p in passes.values() if p]
    if not runs:
        return 0.0, 0.0, 0.0
    n = len(runs)
    at_1 = sum(sum(r) / len(r) for r in runs) / n
    return at_1, sum(all(r) for r in runs) / n, sum(any(r) for r in runs) / n


def _program(runtime: str) -> str:
    if not runtime.strip():
        return "?"
    try:
        words = shlex.split(runtime)
    except ValueError:
        return ""
    return PurePath(words[0]).name if words else "?"


def setup_name(setup: Setup) -> str:
    """`[agent <a>: ]<program> <model> instructions <digest>[ with memory]`."""
    prefix = f"agent {setup.agent}: " if setup.agent else ""
    model = setup.model or "default model"
    memory = " with memory" if setup.memory else ""
    return f"{prefix}{_program(setup.runtime)} {model} instructions {setup.instructions}{memory}"


def _percent(share: float) -> str:
    return f"{share * 100:.0f}"


def _passes(record: EvalRecord) -> dict[str, list[bool]]:
    found: dict[str, list[bool]] = {}
    for run in sorted(record.task_runs, key=lambda r: (r.task_id, r.run_no)):
        if run.role is Role.BUILD:
            found.setdefault(run.task_id, []).append(bool(run.passed))
    return found


def _line(record: EvalRecord) -> str:
    name = setup_name(record.setup)
    if record.kind is Kind.REVIEW:
        return (
            f"{name} review: {record.runs} runs per task, caught {_percent(record.caught or 0)}%,"
            f" {record.false_findings or 0:.2f} false findings per clean run, ${record.cost:.2f}"
        )
    at_k = record.pass_at_k if record.pass_at_k is not None else scores(_passes(record))[2]
    tokens = f", {record.tokens} tokens" if record.tokens is not None else ""
    return (
        f"{record.setup.stage}: {name}: {record.runs} runs per task,"
        f" pass@1 {_percent(record.pass_at_1 or 0)}%, pass@k {_percent(at_k)}%,"
        f" pass^k {_percent(record.pass_k or 0)}%{tokens}, ${record.cost:.2f}"
    )


def report_lines(records: Sequence[EvalRecord]) -> list[str]:
    """One line per record, oldest first; only the newest record of a named agent."""
    newest: dict[str, int] = {}
    for index, record in enumerate(records):
        if record.setup.agent:
            newest[record.setup.agent] = index
    return [
        _line(r) for i, r in enumerate(records) if not r.setup.agent or newest[r.setup.agent] == i
    ]


def _builds(records: Sequence[EvalRecord]) -> list[EvalRecord]:
    return [r for r in records if r.kind is Kind.BUILD]


def pick_pair(
    records: Sequence[EvalRecord], agents: Sequence[str] = ()
) -> tuple[EvalRecord, EvalRecord] | str:
    """(baseline, candidate), or why there is nothing to compare."""
    builds = _builds(records)
    if agents:
        if len(agents) != 2:  # noqa: PLR2004  # a pair
            return "name two agents, each with --agent"
        chosen = []
        for agent in agents:
            theirs = [r for r in builds if r.setup.agent == agent]
            if not theirs:
                return f"has no recorded run of agent {agent}"
            chosen.append(theirs[-1])
        return chosen[0], chosen[1]
    if not builds:
        return "no recorded run"
    candidate = builds[-1]
    earlier = [r for r in builds[:-1] if r.setup != candidate.setup]
    if not earlier:
        return "runs of one setup only"
    return earlier[-1], candidate


def _shares(record: EvalRecord, tasks: set[str]) -> tuple[int, int]:
    passes = {t: p for t, p in _passes(record).items() if t in tasks}
    at_1, at_all, _ = scores(passes)
    return round(at_1 * 100), round(at_all * 100)


def compare(records: Sequence[EvalRecord], agents: Sequence[str] = ()) -> Comparison:
    """Whether the candidate loses to the baseline on the tasks both ran."""
    pair = pick_pair(records, agents)
    if isinstance(pair, str):
        return Comparison(lines=(f"nothing to compare: {pair}",), loses=True)
    baseline, candidate = pair
    tasks = set(_passes(baseline)) & set(_passes(candidate))
    if not tasks:
        return Comparison(lines=("nothing to compare: share no task",), loses=True)
    b1, bk = _shares(baseline, tasks)
    c1, ck = _shares(candidate, tasks)
    over = f"over {len(tasks)} tasks"
    lines = [
        f"baseline: {setup_name(baseline.setup)}: pass@1 {b1}%, pass^k {bk}% {over}",
        f"candidate: {setup_name(candidate.setup)}: pass@1 {c1}%, pass^k {ck}% {over}",
    ]
    if c1 >= b1 and ck >= bk:
        lines.append(f"does not lose: pass@1 {c1 - b1:+d} points, pass^k {ck - bk:+d} points")
        return Comparison(lines=tuple(lines), loses=False)
    lost = [f"pass@1 {c1 - b1:+d} points"] if c1 < b1 else []
    lost += [f"pass^k {ck - bk:+d} points"] if ck < bk else []
    lines.append("loses: " + ", ".join(lost))
    return Comparison(lines=tuple(lines), loses=True)
