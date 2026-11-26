#!/bin/sh
# Start the local stack and print a fresh one-time sign-in link.
set -eu
cd "$(dirname "$0")/.."
docker compose up --detach --wait
docker compose exec -T factory code-factory-container sign-in
