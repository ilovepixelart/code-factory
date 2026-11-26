#!/bin/sh
# Supply-chain audit: known vulnerabilities and adverse project statuses in uv.lock (OSV).
# Needs the network and is not part of the offline gate. `uv audit` is experimental in uv 0.13.9;
# it runs without a flag and prints a warning, which --preview-features audit-command silences.
# A finding is fixed, or ignored by id with a dated reason (--ignore, --ignore-until-fixed).
set -eu
cd "$(dirname "$0")/.."
if [ "${1:-}" = "--changed" ]; then
  shift
  locks=$(uv run --no-sync python scripts/gate_delta.py lockfiles "$@")
  for lock in $locks; do
    case $lock in
      uv.lock) uv audit --locked --preview-features audit-command ;;
      site/uv.lock) uv audit --project site --locked --preview-features audit-command ;;
      web/pnpm-lock.yaml) pnpm --dir web audit ;;
    esac
  done
  exit 0
fi
exec uv audit --locked --preview-features audit-command
