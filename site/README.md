# The code-factory landing page

From the repository root, one command rebuilds the stylesheet and serves the page live at
<http://127.0.0.1:8100>, reloading on every edit; `build` writes the static files instead:

    sh scripts/site.sh             # PORT=8101 for another port
    sh scripts/site.sh build [BASE]

The steps it runs, one by one:

The page is static HTML, built from the templates in `web/templates`:

    uv run python build_static.py [BASE]    # writes dist/; BASE is the path it is served under

The build fails on a local link that resolves to no file it wrote. The same templates render live
while you edit them, which is the only reason this is a FastAPI app rather than a folder of files:

    uv run uvicorn web.app:app --port 8100

The htmx example switcher only ever does a GET for HTML, which a file on disk answers as well as a
route, so it works in both renders.

Every snippet the page shows is in `web/snippets.toml`; `tests/site/test_site_snippets.py` holds
each one to the board: an MCP call to the tool listings in `tests/golden/mcp/`, a command line to
the `code-factory` parser, a config to the rules of `code-factory config check`. The version is
read from the project's `pyproject.toml`.

The stylesheet is built with Tailwind's CLI, at the version the web app uses, and committed:

    pnpm dlx @tailwindcss/cli@4.3.3 -i styles/input.css -o web/static/app.css --minify

`tests/site/test_site_css.py` fails when the markup uses a utility the committed file lacks, which
is what a forgotten rebuild looks like. The theme tokens are the web app's
(`web/src/styles/app.css`); copy a change there into `styles/input.css`.

The landing page describes the local board and shows tested command examples. Start the sample
board with `sh scripts/demo.sh` from the repository root to try its interface.
