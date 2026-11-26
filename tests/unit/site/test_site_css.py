"""The committed stylesheet of the landing page holds every utility its markup names.

Tailwind emits only the classes it finds when it scans the templates, and the result is
committed. A class changed without a rebuild simply does not exist: the page loses that padding,
column or size with no error anywhere.
"""

import re

from repo_files import ROOT

SITE = ROOT / "site"
CSS = SITE / "web" / "static" / "app.css"
TEMPLATES = sorted((SITE / "web" / "templates").rglob("*.html"))
REBUILD = "pnpm dlx @tailwindcss/cli@4.3.3 -i styles/input.css -o web/static/app.css --minify"

# Utilities whose absence changes the layout or a colour token; variants (sm:, dark:, hover:) are
# checked as the selector Tailwind writes for them.
UTILITY = re.compile(
    r"^(p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|gap|gap-x|gap-y|w|h|size|max-w|min-w|grid-cols|"
    r"text|leading|tracking|rounded|border|ring|bg|inset)-[\w./\[\]%-]+$"
)


def _classes(text: str) -> set[str]:
    """Every checked utility in the class attributes and the double quoted `{% set %}` strings.

    base.html keeps the page's spacing in `{% set %}` strings (`band`, `lede`, `cols`, `pad`), so
    reading only attributes would leave the whole vertical rhythm unchecked. A part of an
    attribute written by Jinja is skipped; the literal words around it are kept.
    """
    attrs = re.findall(r'class="([^"]*)"', text)
    sources = [re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", a) for a in attrs]
    sources += re.findall(r'\{%\s*set\s+\w+\s*=\s*"([^"]*)"\s*%\}', text)
    return {
        token
        for source in sources
        for token in source.split()
        if UTILITY.match(token.split(":")[-1]) and "'" not in token
    }


def _unescaped(css: str) -> str:
    """CSS identifier escapes undone, so selectors read as the class names do.

    A leading digit cannot start an identifier, so Tailwind writes `2xl:px-24` as
    `.\\32 xl\\:px-24`.
    """
    return re.sub(r"\\3([0-9a-f]) ", r"\1", css).replace("\\", "")


def _defines(css: str, name: str) -> bool:
    """Whether the stylesheet defines this class, not one that merely starts with its name."""
    return re.search(re.escape(f".{name}") + r"(?![\w./%\[-])", css) is not None


def test_every_utility_the_markup_uses_exists_in_the_stylesheet() -> None:
    css = _unescaped(CSS.read_text(encoding="utf-8"))
    used = set().union(*(_classes(t.read_text(encoding="utf-8")) for t in TEMPLATES))
    assert len(used) > 50, "found too few classes in the templates: the scan is broken"
    missing = sorted(c for c in used if not _defines(css, c))
    assert missing == [], f"absent from app.css, so they do nothing: {missing}. Rebuild: {REBUILD}"


def test_a_utility_missing_from_the_stylesheet_is_found() -> None:
    assert _classes('<a class="mt-8 px-[13px] {{ x }} hover:bg-muted">') == {
        "mt-8",
        "px-[13px]",
        "hover:bg-muted",
    }
    assert not _defines(_unescaped(".px-2\\.5{}"), "px-2")
    assert _defines(_unescaped(".\\32 xl\\:px-24{}"), "2xl:px-24")


def test_no_section_writes_its_own_vertical_padding() -> None:
    """The page's vertical rhythm is one token, `band`, defined in base.html."""
    index = (SITE / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    sections = re.findall(r"<section[^>]*>", index)
    assert sections
    offenders = [tag for tag in sections if re.search(r"\b(py|pt|pb)-[0-9.]+", tag)]
    assert offenders == []
