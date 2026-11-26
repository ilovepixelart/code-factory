#!/bin/sh
set -eu

password=$(cat /credentials/postgres-password)
case "$password" in
  '' | *[!0123456789abcdef]*) echo 'The Compose database password is invalid.' >&2; exit 1 ;;
esac
export CODE_FACTORY_DATABASE_URL="postgresql+asyncpg://code_factory:$password@db:5432/code_factory"
unset password

if [ "${1:-}" = serve ]; then
  code-factory db upgrade
  shift
  set -- serve --no-open "$@"
fi
exec code-factory "$@"
