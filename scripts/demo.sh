#!/bin/sh
# The demo board in one command: a board in use, with data on every page, to look at and polish
# the web app. It drops and rebuilds the schema `demo` of the test database, loads the `demo`
# sample into it (git repositories and transcripts under CODE_FACTORY_DEMO_STATE), builds the web
# app and serves it on port 4321 with the browser opened signed in. It never touches the
# code_factory database or a board on another port; the sample commands refuse anything but a
# _test database. Arguments go to `code-factory serve`.
set -eu
cd "$(dirname "$0")/.."

TEST_DATABASE=${CODE_FACTORY_TEST_DATABASE:-code_factory_test}
# The name goes into a URL: plain lowercase words only, so no query or host can ride along.
case $TEST_DATABASE in
  "" | _test | *[!abcdefghijklmnopqrstuvwxyz0123456789_]*) invalid=1 ;;
  *_test) invalid=0 ;;
  *) invalid=1 ;;
esac
if [ "$invalid" = 1 ]; then
  echo "demo: CODE_FACTORY_TEST_DATABASE must match [a-z0-9_]+_test" >&2
  exit 1
fi

# No password in the URL: the board reads it from the keychain item code-factory-postgres.
CODE_FACTORY_DATABASE_URL="postgresql+asyncpg://code_factory@127.0.0.1:5432/$TEST_DATABASE"
CODE_FACTORY_DB_SCHEMA=demo
CODE_FACTORY_STATE_DIR=${CODE_FACTORY_DEMO_STATE:-$HOME/.local/state/code-factory-demo}
CODE_FACTORY_PORT=${CODE_FACTORY_DEMO_PORT:-4321}
export CODE_FACTORY_DATABASE_URL CODE_FACTORY_DB_SCHEMA CODE_FACTORY_STATE_DIR CODE_FACTORY_PORT

uv sync --locked
pnpm --dir web install --frozen-lockfile
pnpm --dir web build
uv run code-factory sample-drop
# What the last demo wrote: its repositories and transcripts, and the spool its sessions left.
rm -rf "$CODE_FACTORY_STATE_DIR/demo" "$CODE_FACTORY_STATE_DIR/spool"
uv run code-factory sample-prepare
uv run code-factory sample-load demo
exec uv run code-factory serve "$@"
