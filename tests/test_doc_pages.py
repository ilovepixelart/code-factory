"""The Markdown pages: every relative link and anchor resolves, and the operations guide's table of
process variables names each one the code reads, with its default."""

import re
from pathlib import Path

import pytest

from code_factory.checks.module import concurrency
from code_factory.checks.rules.heavy import wait_bound
from code_factory.stages.module import observe_period
from repo_files import ROOT

PAGES = sorted([ROOT / "README.md", *(ROOT / "docs").rglob("*.md")])
OPERATIONS = ROOT / "docs" / "guides" / "operations.md"
LINK = re.compile(r"\]\((?!https?:|mailto:|#)([^)\s]+)\)")


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9 _-]", "", title.strip().lower()).replace(" ", "-")


def _headings(page: Path) -> set[str]:
    text = re.sub(
        r"^```.*?^```", "", page.read_text(encoding="utf-8"), flags=re.MULTILINE | re.DOTALL
    )
    return {_slug(title) for title in re.findall(r"^#+ (.+)$", text, flags=re.MULTILINE)}


def _links(page: Path) -> list[tuple[Path, str]]:
    text = re.sub(
        r"^```.*?^```", "", page.read_text(encoding="utf-8"), flags=re.MULTILINE | re.DOTALL
    )
    found: list[tuple[Path, str]] = []
    for target in LINK.findall(text):
        path, _, anchor = target.partition("#")
        found.append(((page.parent / path).resolve(), anchor))
    return found


@pytest.mark.parametrize("page", PAGES, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_relative_link_resolves_to_a_file_and_a_heading(page: Path) -> None:
    broken = [
        f"{target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}#{anchor}"
        for target, anchor in _links(page)
        if not target.exists()
        or (anchor and target.suffix == ".md" and anchor not in _headings(target))
    ]
    assert not broken, f"{page.relative_to(ROOT)} links to what does not exist: {broken}"


def _tuning_rows() -> dict[str, tuple[str, str]]:
    section = OPERATIONS.read_text(encoding="utf-8").split("## Process tuning", 1)[1]
    section = section.split("\n## ", 1)[0]
    rows = re.findall(
        r"^\| `(CODE_FACTORY_[A-Z_]+)` \| `([^`]+)` \| .* \| `([^`]+)` \|$", section, re.MULTILINE
    )
    return {name: (default, source) for name, default, source in rows}


def test_the_tuning_table_names_every_period_the_code_reads_and_where() -> None:
    rows = _tuning_rows()
    source = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src").rglob("*.py"))
    periods = set(re.findall(r"\"(CODE_FACTORY_[A-Z_]+_SECONDS)\"", source))
    assert periods <= set(rows)
    for name, (_, path) in rows.items():
        assert name in (ROOT / "src" / "code_factory" / path).read_text(encoding="utf-8"), name


def test_the_tuning_table_gives_each_default() -> None:
    rows = _tuning_rows()
    assert rows["CODE_FACTORY_STAGE_OBSERVE_SECONDS"][0] == f"{observe_period({}):g}"
    assert rows["CODE_FACTORY_CHECKS_CONCURRENCY"][0] == str(concurrency({}))
    assert rows["CODE_FACTORY_HEAVY_WAIT"][0] == str(wait_bound(None))
    for name in ("FOLLOWER", "DELIVERY", "PUSH"):
        variable = f"CODE_FACTORY_{name}_SECONDS"
        default, path = rows[variable]
        code = (ROOT / "src" / "code_factory" / path).read_text(encoding="utf-8")
        assert f'os.environ.get("{variable}", "{default}")' in code
