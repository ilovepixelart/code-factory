"""The tool list is the product surface: its shape is pinned, and the rules every tool follows."""

from pathlib import Path

from repo_files import ROOT

GOLDEN = ROOT / "tests" / "support" / "golden" / "mcp"
# Bytes a build run's tool list costs on every connection: what the model reads (descriptions and
# input schemas) and the whole list with the output schemas.


def test_the_golden_folder_holds_only_the_pinned_lists() -> None:
    assert sorted(path.name for path in Path(GOLDEN).iterdir()) == [
        "tools.owner.json",
        "tools.run-build.json",
    ]
