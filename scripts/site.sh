#!/bin/sh
# The landing page in one command. With no argument: rebuild the stylesheet, then serve the page
# live at http://127.0.0.1:8100 and open it. `build [BASE]`: rebuild the stylesheet and write the
# static files to site/dist, failing on a broken local link. PORT sets another port.
set -eu
cd "$(dirname "$0")/../site"

case ${1:-serve} in
  serve | build) ;;
  *)
    echo "site.sh: unknown command '$1'; run 'sh scripts/site.sh' to serve or 'sh scripts/site.sh build' to build" >&2
    exit 2
    ;;
esac

pnpm dlx @tailwindcss/cli@4.3.3 -i styles/input.css -o web/static/app.css --minify

case ${1:-serve} in
  serve)
    port=${PORT:-8100}
    (sleep 1 && open "http://127.0.0.1:$port/") &
    exec uv run uvicorn web.app:app --port "$port" --reload
    ;;
  build)
    shift
    exec uv run python build_static.py "$@"
    ;;
esac
