"""Measure coverage of executable lines introduced by the branch."""

import argparse
import json
import re
from pathlib import Path

from gate_delta import current, git, paths, test_file

ADDED_RANGE = re.compile(rb"^@@ .* \+(\d+)(?:,(\d+))? @@")


def changed_lines(base: str, path: str) -> set[int]:
    """Return working-copy line numbers on the added side of each hunk."""
    if git(
        "--literal-pathspecs", "ls-files", "--error-unmatch", "--", path, check=False
    ).returncode:
        return set(range(1, len(current(path).splitlines()) + 1))
    patch = git(
        "--literal-pathspecs",
        "diff",
        "--unified=0",
        "--no-ext-diff",
        "--no-textconv",
        base,
        "--",
        path,
    ).stdout
    added: set[int] = set()
    for line in patch.splitlines():
        if match := ADDED_RANGE.match(line):
            start = int(match[1])
            added.update(range(start, start + int(match[2] or b"1")))
    return added


def python_report(path: Path) -> dict[str, dict[int, bool]]:
    """Read executable statement lines from coverage.py."""
    report = json.loads(path.read_text(encoding="utf-8"))
    return {
        filename: {
            **dict.fromkeys(data["executed_lines"], True),
            **dict.fromkeys(data["missing_lines"], False),
        }
        for filename, data in report["files"].items()
    }


def vue_report(path: Path) -> dict[str, dict[int, bool]]:
    """Read Vitest LCOV records, whose paths are relative to the web project."""
    result: dict[str, dict[int, bool]] = {}
    lines: dict[int, bool] = {}
    for record in path.read_text(encoding="utf-8").splitlines():
        if record.startswith("SF:"):
            source = Path(record[3:])
            if source.is_absolute():
                source = source.relative_to(Path.cwd())
            elif source.parts[0] != "web":
                source = Path("web") / source
            lines = result.setdefault(source.as_posix(), {})
        elif record.startswith("DA:"):
            number, hits, *_ = record[3:].split(",")
            line = int(number)
            lines[line] = lines.get(line, False) or int(hits) > 0
    return result


def production(path: str) -> bool:
    """Match the production source trees covered by the two runners."""
    return not test_file(path) and (
        (path.startswith("src/code_factory/") and path.endswith(".py"))
        or (
            path.startswith("web/src/")
            and not path.startswith(("web/src/generated/", "web/src/test/"))
            and not path.endswith(".d.ts")
            and path.endswith((".ts", ".vue"))
        )
    )


def assess(base: str, report: dict[str, dict[int, bool]], floor: float) -> int:
    """Fail for missing reports or when changed executable lines miss the floor."""
    covered = total = 0
    refused = False
    for path in filter(production, paths(base)):
        added = changed_lines(base, path)
        if not added or not current(path).strip():
            continue
        if path not in report:
            refused = True
            print(f"Changed coverage: {path!r} is missing from the report.")
            continue
        lines = report[path]
        executable = added & lines.keys()
        hits = sum(lines[line] for line in executable)
        covered += hits
        total += len(executable)
        if hits < len(executable):
            untested = ", ".join(str(line) for line in sorted(executable) if not lines[line])
            print(f"Changed coverage: {path!r} has uncovered lines {untested}.")
        if (
            executable
            and 100 * hits / len(executable) < floor
            and git("cat-file", "-e", f"{base}:{path}", check=False).returncode
        ):
            refused = True
            print(f"Changed coverage: new file {path!r} is below {floor:g}%.")
    if total:
        print(f"Changed coverage: {covered}/{total} executable lines ({covered / total:.1%}).")
    elif not refused:
        print("Changed coverage: no changed executable lines.")
    return int(refused or (total > 0 and 100 * covered / total < floor))


def main() -> int:
    """Evaluate two completed coverage reports against the selected base."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("python", type=Path)
    parser.add_argument("vue", type=Path)
    parser.add_argument("--floor", type=float, default=90.0, choices=range(101), metavar="PERCENT")
    args = parser.parse_args()
    return assess(args.base, python_report(args.python) | vue_report(args.vue), args.floor)


if __name__ == "__main__":
    raise SystemExit(main())
