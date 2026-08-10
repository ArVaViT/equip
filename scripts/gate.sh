#!/usr/bin/env bash
#
# The local gate: every check CI runs, in CI's order, in one command.
#
# This exists because of a specific recurring waste, not as ceremony. Running
# the checks one at a time invites a particular slip: verify, then edit one more
# thing, then push — and the edit is exactly what CI catches. It cost two
# round-trips in one afternoon (a test helper's arity, then a file formatted
# before three tests were appended to it). Both would have been caught by
# re-running everything once, at the end.
#
#   ./scripts/gate.sh            # everything
#   ./scripts/gate.sh backend    # backend only
#   ./scripts/gate.sh frontend   # frontend only
#
# Deliberately NOT a pre-commit hook. A hook that runs a 20-second test suite on
# every commit teaches people to pass --no-verify, and then it protects nothing.
# This is one command you run before you push, and it tells you what CI will say.

set -uo pipefail

cd "$(dirname "$0")/.."

SCOPE="${1:-all}"
FAILED=()

run() {
  local label="$1"
  shift
  printf '\n\033[1m▸ %s\033[0m\n' "$label"
  if "$@"; then
    return 0
  fi
  FAILED+=("$label")
  return 0   # keep going: one command should report every failure, not the first
}

if [[ "$SCOPE" == "all" || "$SCOPE" == "backend" ]]; then
  PY=backend/.venv/bin/python
  if [[ ! -x "$PY" ]]; then
    echo "backend/.venv not found — create it before running the gate" >&2
    exit 1
  fi
  # Same order as .github/workflows/backend-ci.yml, so a failure here reads the
  # same as a failure there.
  # Run from inside backend/ so ruff.toml, mypy.ini and pytest.ini are found
  # exactly the way CI finds them.
  run "ruff check"        env -C backend .venv/bin/python -m ruff check app/ tests/
  run "ruff format"       env -C backend .venv/bin/python -m ruff format app/ tests/ --check
  run "mypy"              env -C backend .venv/bin/python -m mypy --config-file mypy.ini
  run "pytest"            env -C backend .venv/bin/python -m pytest -q
fi

if [[ "$SCOPE" == "all" || "$SCOPE" == "frontend" ]]; then
  # `tsc --noEmit` covers test files too, which `vite build` does not — the arity
  # slip above passed the build and failed the typecheck.
  # From inside frontend/ so tsconfig.json and vitest.config.ts are picked up —
  # `npm --prefix` sets the package but not the working directory, and tsc with
  # no tsconfig in sight quietly prints its own help and exits 1.
  run "tsc"               env -C frontend npx tsc --noEmit
  run "eslint"            env -C frontend npm run --silent lint
  run "i18n"              env -C frontend npm run --silent i18n:check
  # `--localstorage-file` is required for `window.localStorage` to exist under
  # this Node build. Without it 33 tests fail on a clean checkout, on a machine
  # where CI is green — and a gate that fails on an untouched tree is a gate
  # people learn to ignore.
  run "vitest"            env -C frontend NODE_OPTIONS="--localstorage-file=${TMPDIR:-/tmp}/equip-vitest-localstorage.json" npx vitest run
fi

echo
if [[ ${#FAILED[@]} -eq 0 ]]; then
  printf '\033[32m✓ gate passed — this is what CI will say\033[0m\n'
  exit 0
fi

printf '\033[31m✗ %d failed: %s\033[0m\n' "${#FAILED[@]}" "${FAILED[*]}"
exit 1
