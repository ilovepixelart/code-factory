#!/bin/sh
# Start the board with an existing database, or pass --local to provision its own PostgreSQL.
# Remaining arguments go to code-factory serve.
set -eu
cd "$(dirname "$0")/.."

local_db=false
if [ "${1:-}" = --local ]; then
    local_db=true
    shift
    if ! docker compose version >/dev/null 2>&1; then
        printf 'Install Docker with the Compose plugin before using --local.\n' >&2
        exit 1
    fi
    if ! docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
        printf 'Start Docker and check that this terminal can reach it, then retry.\n' >&2
        exit 1
    fi
fi

for tool in uv pnpm; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'Missing %s. Install the prerequisites in docs/quickstart.md.\n' "$tool" >&2
        exit 1
    fi
done

native_compose() {
    docker compose --project-name "${CODE_FACTORY_NATIVE_PROJECT:-code-factory}" \
        -f compose.yaml -f compose.native.yaml "$@"
}

uv sync --locked
pnpm --dir web install --frozen-lockfile
pnpm --dir web build

if [ "$local_db" = true ]; then
    native_compose up --detach --wait db
    address=$(native_compose port db 5432)
    case "$address" in
        127.0.0.1:*) ;;
        *) printf 'Expected a loopback PostgreSQL address, got %s.\n' "$address" >&2; exit 1 ;;
    esac
    password=$(native_compose exec -T db cat /credentials/postgres-password)
    export CODE_FACTORY_DATABASE_URL="postgresql+asyncpg://code_factory:$password@$address/code_factory"
    export CODE_FACTORY_DB_SCHEMA=public
    export CODE_FACTORY_STATE_DIR="${CODE_FACTORY_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/code-factory-native}"
    export CODE_FACTORY_RELEASES_DIR="${CODE_FACTORY_RELEASES_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/code-factory-native/releases}"
    export CODE_FACTORY_RUN_DIR="${CODE_FACTORY_RUN_DIR:-${XDG_RUNTIME_DIR:-/tmp}/code-factory-native-$(id -u)}"
    unset password
    uv run --no-sync code-factory db upgrade
else
    uv run --no-sync code-factory db check
fi

exec uv run --no-sync code-factory serve "$@"
