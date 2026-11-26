"""Render the site to static HTML in dist/.

The htmx example switcher only ever does a GET for HTML, which a file on disk answers as well as
a route, so `static=True` changes nothing but the extension it asks for.

    uv run python build_static.py [BASE]

BASE is the path the page is served under, for example /code-factory; empty for the root.
"""

import re
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from web.app import EXAMPLES, configure, context

HERE = Path(__file__).parent
DIST = HERE / "dist"
_LINK = re.compile(r'(?:href|src|hx-get|hx-post)="([^"]+)"')
_ELSEWHERE = ("http://", "https://", "data:", "#", "mailto:")


def build(base: str) -> list[str]:
    """Write dist/ and return the files written, relative to it."""
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "examples").mkdir(parents=True)
    env = Environment(loader=FileSystemLoader(HERE / "web" / "templates"), autoescape=True)
    configure(env)
    env.globals.update(static=True, base=base)  # ty: ignore[invalid-argument-type]  # see configure
    (DIST / "index.html").write_text(
        env.get_template("index.html").render(**context()), encoding="utf-8"
    )
    for key in EXAMPLES:
        html = env.get_template("partials/example.html").render(**context(key))
        (DIST / "examples" / f"{key}.html").write_text(html, encoding="utf-8")
    shutil.copytree(HERE / "web" / "static", DIST / "assets")
    return sorted(p.relative_to(DIST).as_posix() for p in DIST.rglob("*") if p.is_file())


def problems(base: str, files: list[str]) -> list[str]:
    """Each local link that resolves to no written file, and each placeholder address.

    A static page has no server to notice a 404, so the build checks every link it wrote.
    """
    known = {f"{base}/{f}" for f in files}
    found: list[str] = []
    for page in sorted(DIST.rglob("*.html")):
        for url in _LINK.findall(page.read_text(encoding="utf-8")):
            if url.startswith(_ELSEWHERE):
                if "example.com" in url:
                    found.append(f"{page.name}: placeholder address {url}")
            elif url.split("?")[0] not in known:
                found.append(f"{page.name}: broken link {url}")
    return found


def main() -> int:
    """Build, verify and report."""
    base = sys.argv[1] if len(sys.argv) > 1 else ""
    files = build(base)
    found = problems(base, files)
    for line in found:
        sys.stderr.write(f"{line}\n")
    if found:
        return 1
    sys.stdout.write(f"wrote {len(files)} files to dist/, every local link resolves\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
