"""What a checks log says and how a run ended.

The grammar is the gate's: `gate: <step> starts|due|passed in <n>s|failed (exit <code>)...`, plus
cargo's and pytest's own failure forms.
"""

import re

from code_factory.stages.models import LogReading

CONTAINER_UNAVAILABLE = "checks container unavailable"
BUILD_FAILED = "build failed"
BUILD_ENVIRONMENT = "build failed: environment"
_KILLS = frozenset({137, 143, -9, -15})
_STEP = re.compile(r"[A-Za-z0-9-]+")
_FAILURE = re.compile(r"\b(fail|failed|error|panicked)\b", re.IGNORECASE)
_LIBTEST_FAILED = re.compile(r"^\s*test (\S+) \.\.\. FAILED\s*$", re.MULTILINE)
_PYTEST_FAILED = re.compile(r"^FAILED (\S+)", re.MULTILINE)
# A line that starts FAIL or FAILED, or one that ends "... FAILED".
_TEST_FAILED = (
    re.compile(r"^\s*FAIL(?:ED)?\b", re.MULTILINE),
    re.compile(r"\.\.\. FAILED\s*$", re.MULTILINE),
)
_RUST_ERROR = re.compile(
    r"^\s*(error\[E\d{4}\]|error: could not compile|error: linking with)", re.MULTILINE
)
_PYTHON_BUILD = (re.compile(r"ERROR collecting "), re.compile(r"^E\s+SyntaxError", re.MULTILINE))
_PYTHON_CAUSE = re.compile(r"^E\s+(\w*(?:Error|Exception))\b", re.MULTILINE)
_RUST_ENVIRONMENT = (
    "error[E0463]",
    "error: linking with",
    "error: could not compile",
    "error: aborting due to",
)
_SECONDS = re.compile(r"\d+", re.ASCII)


def no_verdict(code: int) -> bool:
    """Whether a checks run that exited `code` gave no verdict on the code.

    137 is its container killed and -1 checks that did not start or were stopped before they ended.
    """
    return code in {137, -1}


def killed_by_system(code: int) -> bool:
    """Whether `code` is how a run ended when the system, not the checks, ended it."""
    return code in _KILLS


def _gate_lines(log: str) -> list[tuple[str, str]]:
    """Each `gate: <step> <rest>` line as `(step, rest)`, the step split at the first space."""
    found = []
    for line in log.splitlines():
        head = line.removeprefix("gate: ")
        if head != line and " " in head:
            step, rest = head.split(" ", 1)
            found.append((step, rest))
    return found


def _named(step: str) -> bool:
    return _STEP.fullmatch(step) is not None


def killed_run(code: int, log: str) -> bool:
    """Whether a run that exited `code` ending with `log` was killed by the system.

    A kill code and no `gate: <step> failed` line, which a gate prints before it exits for a step
    that failed: the kills measured ended before the gate could print one.
    """
    return killed_by_system(code) and not any(
        rest.startswith("failed") for _, rest in _gate_lines(log)
    )


def last_started_step(log: str) -> str | None:
    """The step a gate log last started, `gate: <step> starts`: where a killed run was."""
    started = [step for step, rest in _gate_lines(log) if rest == "starts" and _named(step)]
    return started[-1] if started else None


def _failing_lines(log: str) -> list[str]:
    lines = log.splitlines()
    found = [line for line in lines if _FAILURE.search(line)]
    return found or lines[-1:]


def _failing_tests(log: str) -> list[str]:
    names = _LIBTEST_FAILED.findall(log) + _PYTEST_FAILED.findall(log)
    return sorted(set(names))


def _environmental(log: str) -> bool:
    rust = [line.lstrip() for line in log.splitlines() if line.lstrip().startswith("error")]
    rust_ok = all(line.startswith(_RUST_ENVIRONMENT) for line in rust)
    if not _any(_PYTHON_BUILD, log):
        return rust_ok
    causes = _PYTHON_CAUSE.findall(log)
    return rust_ok and bool(causes) and all(cause == "ModuleNotFoundError" for cause in causes)


def _any(patterns: tuple[re.Pattern[str], ...], log: str) -> bool:
    return any(pattern.search(log) is not None for pattern in patterns)


def _build_failure(log: str) -> bool:
    built = _RUST_ERROR.search(log) is None and not _any(_PYTHON_BUILD, log)
    return not built and not _any(_TEST_FAILED, log)


def _step_state(rest: str) -> tuple[str, int | None] | None:
    if rest == "due" or rest.startswith("due:"):
        return "due", None
    seconds = rest.removeprefix("passed in ").removesuffix("s")
    if rest.startswith("passed in ") and rest.endswith("s") and _SECONDS.fullmatch(seconds):
        return "passed", int(seconds)
    if rest.startswith("failed (exit "):
        return "failed", None
    return None


def _last_per_step(log: str) -> dict[str, tuple[str, int | None]]:
    steps: dict[str, tuple[str, int | None]] = {}
    for step, rest in _gate_lines(log):
        state = _step_state(rest) if _named(step) else None
        if state is not None:
            steps[step] = state
    return steps


def _lock_waits(log: str) -> list[tuple[str, int]]:
    waits: dict[str, int] = {}
    for step, rest in _gate_lines(log):
        seconds = rest.removeprefix("waited ").removesuffix("s for the heavy-step lock")
        if (
            _named(step)
            and rest.startswith("waited ")
            and rest.endswith("s for the heavy-step lock")
            and _SECONDS.fullmatch(seconds)
        ):
            waits[step] = waits.get(step, 0) + int(seconds)
    return list(waits.items())


def _quarantined(log: str) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for step, rest in _gate_lines(log):
        test = rest.removeprefix("quarantined: ").removesuffix(" failed")
        if _named(step) and rest.startswith("quarantined: ") and rest.endswith(" failed") and test:
            counts[test] = counts.get(test, 0) + 1
    return list(counts.items())


def read_log(log: str) -> LogReading:
    """Everything the readers of a checks log say of it."""
    build = _build_failure(log)
    steps = _last_per_step(log)
    flaky = [step for step, rest in _gate_lines(log) if _named(step) and rest.startswith("flaky:")]
    reason = ""
    if build:
        reason = BUILD_ENVIRONMENT if _environmental(log) else BUILD_FAILED
    return LogReading(
        failing_lines=_failing_lines(log),
        failing_tests=_failing_tests(log),
        build_failure=build,
        failure_reason=reason,
        reported_steps=[(step, state) for step, (state, _) in steps.items()],
        step_seconds=[(s, sec) for s, (_, sec) in steps.items() if sec is not None],
        lock_waits=_lock_waits(log),
        quarantined_failures=_quarantined(log),
        flaky_steps=list(dict.fromkeys(flaky)),
    )
