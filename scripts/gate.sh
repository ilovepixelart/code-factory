#!/bin/sh
# The gate. The static checks run first as one && chain, so a red one stops the run; then pytest
# and the web checks run side by side, each writing its whole output to its own log, and the gate
# passes only when both exit 0 (each status is read from `wait`, never through a pipe).
# Python tests use a disposable PostgreSQL database, from the runner or the macOS keychain.
set -eu
cd "$(dirname "$0")/.."

force=0
fast=0
base_ref=""
audit=0
secrets=0
diff_coverage=0
mutation=0
semgrep_rules=""
spec_receipt=""
part=""
shard=""
while [ "$#" -gt 0 ]; do
  case $1 in
    --force) force=1 ;;
    --fast) fast=1 ;;
    --audit) audit=1 ;;
    --secrets) secrets=1 ;;
    --diff-coverage) diff_coverage=1 ;;
    --mutation) mutation=1 ;;
    --spec-lock)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "gate: --spec-lock needs an owner receipt file" >&2
        exit 2
      fi
      spec_receipt=$2
      shift
      ;;
    --semgrep)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "gate: --semgrep needs a local rules file" >&2
        exit 2
      fi
      semgrep_rules=$2
      shift
      ;;
    --part)
      case ${2:-} in
        static | backend-unit | backend-integration | backend-e2e | web) part=$2 ;;
        *)
          echo "gate: --part takes static, backend-unit, backend-integration, backend-e2e or web" >&2
          exit 2
          ;;
      esac
      shift
      ;;
    --shard)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "gate: --shard needs INDEX/COUNT, such as 1/2" >&2
        exit 2
      fi
      shard=$2
      shift
      ;;
    --base)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "gate: --base needs a Git ref" >&2
        exit 2
      fi
      base_ref=$2
      shift
      ;;
    *)
      echo "usage: sh scripts/gate.sh [--force] [--fast] [--part PART [--shard I/N]] [--base REF] [--secrets] [--audit]" >&2
      echo "       [--diff-coverage] [--semgrep FILE] [--spec-lock FILE] [--mutation]" >&2
      exit 2
      ;;
  esac
  shift
done

delta() {
  if [ -n "$base_ref" ]; then
    uv run --no-sync python scripts/gate_delta.py "$1" --base "$base_ref"
  else
    uv run --no-sync python scripts/gate_delta.py "$1"
  fi
}

timed() {
  phase=$1
  shift
  began=$(date +%s)
  echo "gate: $phase starts"
  if "$@"; then
    echo "gate: $phase passed in $(($(date +%s) - began))s"
  else
    status=$?
    echo "gate: $phase failed (exit $status)"
    return "$status"
  fi
}

KEYCHAIN_ACCOUNT=code_factory
KEYCHAIN_SERVICE=code-factory-postgres
TEST_DATABASE=${CODE_FACTORY_TEST_DATABASE:-code_factory_test}
# The name goes into a URL: plain lowercase words only, so no query or host can ride along.
# The letters are spelled out so the locale cannot widen a range.
case $TEST_DATABASE in
  "" | _test | *[!abcdefghijklmnopqrstuvwxyz0123456789_]*) invalid_test_database=1 ;;
  *_test) invalid_test_database=0 ;;
  *) invalid_test_database=1 ;;
esac
if [ "$invalid_test_database" = 1 ]; then
  echo "gate: CODE_FACTORY_TEST_DATABASE must match [a-z0-9_]+_test (lowercase letters, digits and underscores, ending in _test)" >&2
  exit 1
fi

runner_database_url=${CODE_FACTORY_GATE_DATABASE_URL:-}
unset CODE_FACTORY_GATE_DATABASE_URL CODE_FACTORY_DATABASE_URL

prepare_database() {
  if [ -n "$runner_database_url" ]; then
    CODE_FACTORY_GATE_DATABASE_URL=$runner_database_url PYTHONPATH=tests/support uv run --no-sync python -c '
import os
from database_guard import UnsafeDatabaseError, assert_test_database

try:
    assert_test_database(os.environ["CODE_FACTORY_GATE_DATABASE_URL"])
except UnsafeDatabaseError as error:
    raise SystemExit(str(error)) from None
' || return 1
    CODE_FACTORY_DATABASE_URL=$runner_database_url
  else
    PASSWORD=$(security find-generic-password -a "$KEYCHAIN_ACCOUNT" -s "$KEYCHAIN_SERVICE" -w 2>/dev/null) || {
      echo "gate: no keychain entry (account $KEYCHAIN_ACCOUNT, service $KEYCHAIN_SERVICE); see README.md" >&2
      return 1
    }
    CODE_FACTORY_DATABASE_URL="postgresql+asyncpg://$KEYCHAIN_ACCOUNT:$PASSWORD@127.0.0.1:5432/$TEST_DATABASE"
  fi
  export CODE_FACTORY_DATABASE_URL

  uv run --no-sync --quiet code-factory db check >/dev/null 2>&1 ||
    uv run --no-sync --quiet code-factory db upgrade >/dev/null 2>&1 || {
    echo "gate: could not read or migrate the test database; check the runner's database settings" >&2
    return 1
  }
}

# The old name must appear in no commit message (tests/unit/test_no_old_name.py covers files).
# Words are assembled so this script does not match itself.
OLD_NAME="whole""cycle"
OLD_ABBREVIATION="W""C"
no_old_name_in_commits() {
  if git rev-parse --verify --quiet HEAD >/dev/null; then
    ! git log --format=%B | grep -iE "$OLD_NAME|whole[-_ ]cycle" >/dev/null &&
    ! git log --format=%B | grep -E "(^|[^[:alnum:]_])($OLD_ABBREVIATION([^[:alnum:]_]|\$)|$(echo $OLD_ABBREVIATION | tr A-Z a-z)-)" >/dev/null
  fi
}

web_install() {
  command -v pnpm >/dev/null 2>&1 || {
    echo "gate: pnpm is not on PATH; install Node 26 and pnpm (see README.md) and retry" >&2
    return 1
  }
  if [ "${CODE_FACTORY_OFFLINE:-}" = 1 ]; then
    pnpm --dir web install --frozen-lockfile --offline
  else
    pnpm --dir web install --frozen-lockfile
  fi
}

# The database URL holds the password, and none of the web steps reads it.
web_checks() (
  unset CODE_FACTORY_DATABASE_URL
  timed web-install web_install &&
    timed web-lint pnpm --dir web lint &&
    timed web-typecheck pnpm --dir web typecheck &&
    timed web-format pnpm --dir web format:check &&
    timed web-unused pnpm --dir web unused &&
    timed web-test pnpm --dir web test --maxWorkers="$WEB_TEST_WORKERS"
)
# The build empties and rewrites the directory the app serves, which pytest reads while it builds
# its app, so it runs after pytest has finished.
web_build() (
  unset CODE_FACTORY_DATABASE_URL
  pnpm --dir web build
)

# Each pytest worker migrates a schema of its own inside the one test database (tests/conftest.py).
# Five workers took the suite from 261 s on three to about 130 s; gates running at once on one
# machine share it, so set fewer through the variable there.
PYTEST_WORKERS=${CODE_FACTORY_TEST_WORKERS:-5}
FAST_PYTEST_WORKERS=${CODE_FACTORY_FAST_TEST_WORKERS:-4}
# vitest otherwise starts a worker per core in every gate that runs at once.
WEB_TEST_WORKERS=${CODE_FACTORY_WEB_TEST_WORKERS:-2}

prepare() {
  uv lock --check && uv sync --locked && no_old_name_in_commits
}
static_checks() {
  uv run --no-sync ruff format --check . &&
    uv run --no-sync ruff check . &&
    uv run --no-sync ty check &&
    uv run --no-sync lint-imports
}

affected_python() {
  # A module suite can keep several workers busy. Individual files avoid the worker startup cost.
  for target in "$@"; do
    case $target in
      *.py) ;;
      *) uv run --no-sync pytest --no-cov -n "$FAST_PYTEST_WORKERS" --dist worksteal "$@"; return $? ;;
    esac
  done
  uv run --no-sync pytest --no-cov "$@"
}

timed prepare prepare
base=$(delta base)
base_ref=$base
# A part other than `static` runs only its own suite; the checks against the base are static's.
branch_checks=0
[ -n "$part" ] && [ "$part" != static ] || branch_checks=1
[ "$branch_checks" = 0 ] || timed test-delta delta review
if [ "$branch_checks" = 1 ] && [ -n "$spec_receipt" ]; then
  (unset CODE_FACTORY_DATABASE_URL; timed spec-lock uv run --no-sync python scripts/gate_spec_lock.py verify "$spec_receipt")
fi
if [ "$branch_checks" = 0 ]; then
  :
elif [ "$secrets" = 1 ] || command -v gitleaks >/dev/null 2>&1; then
  (unset CODE_FACTORY_DATABASE_URL; timed secrets uv run --no-sync python scripts/gate_scan.py gitleaks "$base")
else
  echo "gate: Gitleaks is unavailable. Use --secrets to require the scan."
fi
if [ "$branch_checks" = 1 ] && [ "$audit" = 1 ]; then
  (unset CODE_FACTORY_DATABASE_URL; timed audit sh scripts/audit.sh --changed --base "$base")
fi
if [ "$branch_checks" = 1 ] && [ -n "$semgrep_rules" ]; then
  (unset CODE_FACTORY_DATABASE_URL; timed semgrep uv run --no-sync python scripts/gate_scan.py semgrep "$base" --config "$semgrep_rules")
fi

if [ "$fast" = 1 ] && [ "$diff_coverage" = 0 ] && [ "$mutation" = 0 ]; then
  selected=$(delta affected)
  if [ "$selected" != full ]; then
    set -f
    tests=$(printf '%s\n' "$selected" | sed -n 's/^python //p')
    if [ -n "$tests" ]; then
      timed database prepare_database
      timed affected-python affected_python $tests
    fi
    if printf '%s\n' "$selected" | grep -qx vue; then
      unset CODE_FACTORY_DATABASE_URL
      timed web-install web_install
      timed affected-web pnpm --dir web exec vitest run --project unit --maxWorkers="$WEB_TEST_WORKERS"
    fi
    if [ -z "$selected" ]; then
      echo "gate: no affected test suites"
    fi
    exit 0
  fi
  echo "gate: shared inputs changed, running the full gate"
fi

# One part of the gate, as a CI job runs it beside the others. Each pytest part checks no coverage
# floor: the parts' coverage files are combined and the floor is checked once, over all of them.
# With --shard a part runs only its share of the folder's test files (scripts/gate_shard.py).
part_tests() {
  if [ -z "$shard" ]; then
    uv run --no-sync pytest -n "$PYTEST_WORKERS" --dist worksteal --cov-fail-under=0 "$1"
    return
  fi
  files=$(uv run --no-sync python scripts/gate_shard.py "$1" "$shard") || return 2
  set -f
  # shellcheck disable=SC2086  # one test file path per word; paths hold no spaces
  uv run --no-sync pytest -n "$PYTEST_WORKERS" --dist worksteal --cov-fail-under=0 $files
}
case $part in
  "") ;;
  static) timed static static_checks; exit 0 ;;
  backend-unit) (unset CODE_FACTORY_DATABASE_URL; timed backend-unit part_tests tests/unit); exit 0 ;;
  backend-integration | backend-e2e)
    timed database prepare_database
    timed "$part" part_tests "tests/${part#backend-}"
    exit 0
    ;;
  web)
    timed web web_checks
    timed build web_build
    exit 0
    ;;
esac

CACHE_FILE=.pytest_cache/code-factory-gate-pass
key=""
if [ "$force" = 0 ] && [ "$diff_coverage" = 0 ] && [ "$mutation" = 0 ]; then
  key=$(uv run --no-sync python scripts/gate_cache.py "$base")
  if [ -n "$key" ] && [ -f "$CACHE_FILE" ] &&
    [ -f src/code_factory/platform/web/dist/index.html ] &&
    [ "$(cat "$CACHE_FILE")" = "$key" ]; then
    echo "gate: this tree and toolchain have already passed"
    exit 0
  fi
fi

timed database prepare_database
timed static static_checks

LOG_DIR=$(mktemp -d "${TMPDIR:-/tmp}/code-factory-gate.XXXXXX")
pytest_pid=""
web_pid=""
# Job control gives each background job a process group of its own, so a signal stops pytest, its
# workers, pnpm and its children together (a plain kill would stop only the first process of each).
set -m
# SIGINT first: pytest then runs its fixture teardown, which drops the schemas its workers built.
# Whatever is still running after the grace period gets SIGTERM.
GRACE_SECONDS=30
signal_jobs() {
  for pid in "$pytest_pid" "$web_pid"; do
    [ -z "$pid" ] || kill "-$1" -- "-$pid" 2>/dev/null || true
  done
}
any_job_alive() {
  for pid in "$pytest_pid" "$web_pid"; do
    [ -z "$pid" ] || ! kill -0 -- "-$pid" 2>/dev/null || return 0
  done
  return 1
}
stop_jobs() {
  signal_jobs INT
  waited=0
  while any_job_alive && [ "$waited" -lt "$GRACE_SECONDS" ]; do
    sleep 1
    waited=$((waited + 1))
  done
  signal_jobs TERM
  wait 2>/dev/null || true
}
trap 'rm -rf "$LOG_DIR"' EXIT
trap 'stop_jobs; exit 130' HUP INT TERM

# worksteal: an idle worker takes queued tests from a busy one, so a slow file never ends alone.
timed pytest uv run --no-sync pytest -n "$PYTEST_WORKERS" --dist worksteal >"$LOG_DIR/pytest.log" 2>&1 &
pytest_pid=$!
timed web web_checks >"$LOG_DIR/web.log" 2>&1 &
web_pid=$!

pytest_status=0
web_status=0
wait "$pytest_pid" || pytest_status=$?
wait "$web_pid" || web_status=$?
build_status=0
if [ "$pytest_status" = 0 ] && [ "$web_status" = 0 ]; then
  timed build web_build >"$LOG_DIR/build.log" 2>&1 &
  web_pid=$!
  wait "$web_pid" || build_status=$?
fi

# A step that passed shows the end of its log (the summary); one that failed shows all of it.
report() {
  if [ "$2" = 0 ]; then
    echo "gate: $1 passed"
    if [ "$1" = web ]; then
      sed -n '/^gate: web-.* passed in [0-9][0-9]*s$/p' "$LOG_DIR/web.log"
    fi
    tail -n 4 "$LOG_DIR/$1.log"
  else
    echo "gate: $1 FAILED (exit $2), full output:" >&2
    cat "$LOG_DIR/$1.log" >&2
  fi
}
report pytest "$pytest_status"
report web "$web_status"
[ ! -f "$LOG_DIR/build.log" ] || report build "$build_status"
[ "$pytest_status" = 0 ] && [ "$web_status" = 0 ] && [ "$build_status" = 0 ] || exit 1
if [ "$diff_coverage" = 1 ]; then
  uv run --no-sync coverage json --fail-under=0 -o "$LOG_DIR/python-coverage.json"
  timed diff-coverage uv run --no-sync python scripts/gate_coverage.py \
    "$base" "$LOG_DIR/python-coverage.json" web/coverage/lcov.info
fi
if [ "$mutation" = 1 ]; then
  timed mutation uv run --no-sync python scripts/gate_mutation.py "$base"
fi
if [ -n "$key" ] && [ "$(uv run --no-sync python scripts/gate_cache.py "$base")" = "$key" ]; then
  mkdir -p .pytest_cache
  temporary=$(mktemp .pytest_cache/code-factory-gate.XXXXXX)
  printf '%s\n' "$key" >"$temporary"
  mv -f "$temporary" "$CACHE_FILE"
fi
