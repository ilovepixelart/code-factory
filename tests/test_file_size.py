from repo_files import ROOT

MAX_LINES = 400


def test_no_source_file_exceeds_the_line_limit() -> None:
    too_long = [
        f"{path.relative_to(ROOT)}: {count} lines"
        for path in sorted((ROOT / "src").rglob("*.py"))
        if (count := len(path.read_text(encoding="utf-8").splitlines())) > MAX_LINES
    ]
    assert not too_long, f"split these files (limit {MAX_LINES} lines):\n" + "\n".join(too_long)
