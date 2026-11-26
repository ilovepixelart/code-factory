#!/bin/sh
# Build the distributable app from the locked frontend and Python sources.
set -eu
cd "$(dirname "$0")/.."
out=dist
if [ "$#" -gt 0 ]; then
  out=$1
fi
pnpm --dir web install --frozen-lockfile
pnpm --dir web build
uv build --out-dir "$out"
