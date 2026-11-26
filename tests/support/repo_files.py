"""The files of the repository: tracked, plus untracked ones that are not ignored."""

import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The one source of the version; tests compare every other place that reports it to this.
PROJECT_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
    "version"
]
# Third-party code copied in verbatim; its text is not ours to rewrite.
VENDORED = "src/code_factory/platform/web/static/docs-assets/swagger-ui/"


def repo_files(*, include_vendored: bool = False) -> list[Path]:
    """Relative paths of every file git knows or would add."""
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],  # noqa: S607
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    names = [name for name in listing.split("\0") if name and (ROOT / name).is_file()]
    return [Path(name) for name in names if include_vendored or not name.startswith(VENDORED)]


def text_lines(path: Path) -> list[str]:
    """Lines of a text file; none for a binary one."""
    try:
        return (ROOT / path).read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []
