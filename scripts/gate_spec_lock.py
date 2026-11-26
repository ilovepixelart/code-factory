"""Prove named pytest checks are red for their expected reason and lock their source files."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

from gate_delta import git, test_file

TIMEOUT = 120
MAX_REPORT_BYTES = 1_000_000


def source(node: str) -> str:
    """The relative tracked Python test file from a single pytest node ID."""
    path, separator, case = node.partition("::")
    file = PurePosixPath(path)
    if (
        not separator
        or not case
        or not path.endswith(".py")
        or not test_file(path)
        or file.is_absolute()
        or file.as_posix() != path
        or ".." in file.parts
        or path.startswith("-")
    ):
        msg = "name a repository-relative pytest node, such as tests/test_example.py::test_case"
        raise ValueError(msg)
    return path


def digest(data: bytes) -> str:
    """The content identifier recorded by the trusted runner."""
    return hashlib.sha256(data).hexdigest()


def checked_file(root: Path, path: str) -> bytes:
    """Read a regular test file whose path traverses no link."""
    file = root / path
    if file.resolve() != file or not file.is_file():
        msg = f"locked file is missing or linked: {path}"
        raise ValueError(msg)
    return file.read_bytes()


def expected_assertion(node: str, reason: str) -> bool:
    """Only one collected case with the exact assertion message can seal a file."""
    with tempfile.TemporaryDirectory(prefix="code-factory-spec-check-") as directory:
        report = Path(directory) / "result.xml"
        result = subprocess.run(  # noqa: S603  # one validated node, no shell
            [sys.executable, "-m", "pytest", "-o", "addopts=", f"--junitxml={report}", "--", node],
            env={key: val for key, val in os.environ.items() if key != "PYTEST_ADDOPTS"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=TIMEOUT,
        )
        if (
            result.returncode != 1
            or not report.is_file()
            or report.stat().st_size > MAX_REPORT_BYTES
        ):
            return False
        xml = ET.parse(report)  # noqa: S314  # bounded report from the trusted spec checkout
        cases = xml.findall(".//testcase")
        if len(cases) != 1:
            return False
        case = cases[0]
        failure = case.find("failure")
        if failure is None or case.find("error") is not None or case.find("skipped") is not None:
            return False
        message = failure.get("message", "").partition("\n")[0]
        return message == f"AssertionError: {reason}"


def seal(root: Path, receipt: Path, checks: list[tuple[str, str]]) -> int:
    """Write an owner receipt only after all named cases fail as expected."""
    where = receipt.resolve()
    if where.is_relative_to(root) or receipt.exists() or receipt.is_symlink():
        msg = "use a new receipt file outside the project checkout"
        raise ValueError(msg)
    head = git("rev-parse", "--verify", "HEAD").stdout.decode().strip()
    if git("diff", "--quiet", "--no-ext-diff", "--no-textconv", head, "--", check=False).returncode:
        msg = "commit the spec tests before running the expected-failure check"
        raise ValueError(msg)
    files: dict[str, str] = {}
    for node, reason in checks:
        path = source(node)
        if not reason or "\n" in reason:
            msg = "the expected assertion message must be one nonempty line"
            raise ValueError(msg)
        files[path] = digest(git("show", f"{head}:{path}").stdout)
        if digest(checked_file(root, path)) != files[path] or not expected_assertion(node, reason):
            print(f"Spec lock refused {node}. The expected assertion did not fail.")
            return 1
    if any(digest(checked_file(root, path)) != value for path, value in files.items()):
        msg = "a sealed test file changed while the expected-failure checks ran"
        raise ValueError(msg)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=where.parent) as temporary:
        json.dump(
            {"commit": head, "nodes": [node for node, _ in checks], "files": files}, temporary
        )
        temporary.flush()
        os.link(temporary.name, where)
    print(f"Locked {len(files)} test files from {head[:12]}.")
    return 0


def verify(root: Path, receipt: Path) -> int:
    """Refuse missing, moved or altered test files in the working tree or index."""
    if receipt.resolve().is_relative_to(root):
        msg = "the spec receipt belongs outside the project checkout"
        raise ValueError(msg)
    lock = json.loads(receipt.read_text(encoding="utf-8"))
    files = lock["files"]
    if (
        not isinstance(files, dict)
        or not files
        or set(files) != {source(node) for node in lock["nodes"]}
    ):
        msg = "the spec receipt has no matching file list"
        raise ValueError(msg)
    changed = []
    for path, expected in files.items():
        try:
            indexed = git("show", f":{path}", check=False)
            work = digest(checked_file(root, path))
        except OSError, ValueError:
            changed.append(path)
            continue
        if indexed.returncode or digest(indexed.stdout) != expected or work != expected:
            changed.append(path)
    for path in changed:
        print(f"Spec lock refused {path!r}. Restore the test file that was sealed.")
    return int(bool(changed))


def main() -> int:
    """Run a human-approved seal or verify an existing receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    sealing = actions.add_parser("seal")
    sealing.add_argument("receipt", type=Path)
    sealing.add_argument(
        "--check", nargs=2, metavar=("NODE", "REASON"), action="append", required=True
    )
    actions.add_parser("verify").add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        root = Path(git("rev-parse", "--show-toplevel").stdout.decode().strip()).resolve()
        receipt = args.receipt.absolute()
        os.chdir(root)
        if args.action == "seal":
            return seal(root, receipt, args.check)
        return verify(root, receipt)
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        KeyError,
        TypeError,
        ET.ParseError,
    ) as error:
        parser.exit(2, f"Spec lock could not be checked: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
