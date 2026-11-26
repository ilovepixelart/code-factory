"""The code-factory landing page.

One set of Jinja templates, rendered two ways: this app while editing them, and `build_static.py`
for the static files. Both read the snippets from `snippets.toml`, the file
`tests/integration/site/test_site_snippets.py` holds to the board, so the page cannot show code the
board refuses.
"""

import hashlib
import tomllib
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers.configs import TOMLLexer
from pygments.lexers.data import JsonLexer
from pygments.lexers.shell import BashLexer

HERE = Path(__file__).parent
# The version the page shows, read from the one place the project keeps it.
VERSION = tomllib.loads((HERE.parent.parent / "pyproject.toml").read_text(encoding="utf-8"))[
    "project"
]["version"]
_SNIPPETS = tomllib.loads((HERE / "snippets.toml").read_text(encoding="utf-8"))
type Snippets = dict[str, dict[str, str]]
EXAMPLES = cast("Snippets", _SNIPPETS["examples"])
PANES = cast("Snippets", _SNIPPETS["panes"])
_LEXERS = {"mcp": JsonLexer, "shell": BashLexer, "toml": TOMLLexer}
# Hashed into `?v=`, so a rebuilt file is fetched rather than read from cache. Content, not
# mtime: a fresh checkout stamps every file with the time it was cloned.
_VERSIONED = ("app.css", "code.css", "site.js", "theme-early.js", "js/htmx.min.js")


def highlighted(snippet: dict[str, str]) -> str:
    """A snippet coloured on the server: the browser receives finished HTML."""
    lexer = _LEXERS[snippet["lang"]]()
    return str(highlight(snippet["source"].strip(), lexer, HtmlFormatter(nowrap=True)))


def asset_v() -> str:
    """A digest of the files served with `?v=`."""
    digest = hashlib.blake2b(digest_size=8)
    for name in _VERSIONED:
        digest.update((HERE / "static" / name).read_bytes())
    return digest.hexdigest()


def configure(env: Environment) -> None:
    """The filters and globals both renders share."""
    env.filters["code"] = highlighted
    # jinja2 types `globals` as the values of its default namespace; any object is a valid global.
    env.globals.update(asset_v=asset_v, version=VERSION, panes=PANES)  # ty: ignore[invalid-argument-type]


def context(chosen: str | None = None) -> dict[str, object]:
    """The example table and the selected entry, the first when `chosen` names none."""
    return {"examples": EXAMPLES, "chosen": chosen if chosen in EXAMPLES else next(iter(EXAMPLES))}


_templates = Jinja2Templates(directory=str(HERE / "templates"))
configure(_templates.env)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/assets", StaticFiles(directory=str(HERE / "static")), name="assets")


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request) -> HTMLResponse:
    """The page."""
    return _templates.TemplateResponse(request, "index.html", context())


@app.get("/examples/{key}", response_class=HTMLResponse)
async def example(request: Request, key: str) -> HTMLResponse:
    """One example, chosen on the server, as the fragment htmx swaps in."""
    return _templates.TemplateResponse(request, "partials/example.html", context(key))
