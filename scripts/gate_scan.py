"""Run explicitly requested security scans on the branch delta."""

import argparse
import shutil
import subprocess
from pathlib import Path

from gate_delta import git, paths


def run(command: list[str], data: bytes | None = None) -> int:
    """Run an installed scanner with redaction set by the caller."""
    return subprocess.run(command, input=data, check=False).returncode  # noqa: S603


def secrets(program: str, base: str) -> int:
    """Inspect branch commits, local tracked changes, and new files Git would add."""
    common = ["--redact=100", "--no-banner"]
    if run([program, "git", *common, f"--log-opts={base}..HEAD", "."]):
        return 1
    patch = git("diff", "--no-ext-diff", "--no-textconv", "HEAD", "--").stdout
    if patch and run([program, "stdin", *common], patch):
        return 1
    names = git(
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
        "--exclude=.claude/worktrees/",
        "--exclude=.code-factory/worktrees/",
    ).stdout
    for name in filter(None, names.decode(errors="surrogateescape").split("\0")):
        path = Path(name)
        if (
            path.is_file()
            and not path.is_symlink()
            and run([program, "stdin", *common], path.read_bytes())
        ):
            print(f"Secret scan refused the new file {name!r}.")
            return 1
    return 0


def main() -> int:
    """Run a scanner against the already resolved commit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scanner", choices=("gitleaks", "semgrep"))
    parser.add_argument("base")
    parser.add_argument("--config")
    args = parser.parse_args()
    program = shutil.which(args.scanner)
    if program is None:
        parser.exit(2, f"Install {args.scanner} before enabling its gate check.\n")
    if args.scanner == "gitleaks":
        return secrets(program, args.base)
    if args.config is None or not Path(args.config).is_file():
        parser.error("Semgrep needs a local rules file")
    changed = [
        name for name in paths(args.base) if Path(name).is_file() and not Path(name).is_symlink()
    ]
    if not changed:
        print("Semgrep: no changed files to scan.")
        return 0
    return run(
        [
            program,
            "scan",
            "--metrics=off",
            "--disable-version-check",
            "--config",
            args.config,
            "--",
            *changed,
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
