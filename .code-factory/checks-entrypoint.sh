#!/bin/sh
# PostgreSQL in this container is disposable. The board runs it with no external network.
set -eu
export HOME=/root
git config --global --add safe.directory "$PWD"
data=$(mktemp -d)
chown postgres:postgres "$data"
password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
password_file=$(mktemp)
trap 'rm -f "$password_file"' EXIT
printf '%s\n' "$password" > "$password_file"
chown postgres:postgres "$password_file"
runuser -u postgres -- initdb -D "$data" --auth-local=trust --auth-host=scram-sha-256 \
  --pwfile="$password_file" --no-instructions >/dev/null
rm -f "$password_file"
trap - EXIT
runuser -u postgres -- pg_ctl -D "$data" -l "$data/server.log" \
  -o "-h 127.0.0.1 -k $data" -w start >/dev/null
runuser -u postgres -- createdb -h "$data" code_factory_test
export CODE_FACTORY_GATE_DATABASE_URL="postgresql+asyncpg://postgres:$password@127.0.0.1/code_factory_test"
exec "$@"
