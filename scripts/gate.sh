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
#   ./scripts/gate.sh a11y       # axe over the real pages (needs `npm run dev`)
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
  #
  # A fresh file per run, deleted after. A fixed path made the gate flaky: the
  # store is SQLite-backed, so a previous run's -wal/-shm siblings can fail the
  # next one for no reason connected to the code. Flaky is worse than absent,
  # for exactly the same reason as above.
  LS_STORE="$(mktemp -d)/localstorage.json"
  run "vitest"            env -C frontend NODE_OPTIONS="--localstorage-file=$LS_STORE" npx vitest run
  rm -rf "$(dirname "$LS_STORE")"
fi

# The a11y check is opt-in — `./scripts/gate.sh a11y` — and not part of `all`.
#
# It is separate because it is the only check here that needs a running server,
# and a gate that boots a dev server on every invocation is a gate that hangs
# on a busy port and gets abandoned. It is *here at all* because on 2026-08-13
# it caught two real defects on two consecutive pushes — a footer line at
# 3.6:1 and a badge at 4.46:1 — and each cost a full CI round-trip to learn,
# which is precisely the waste this script was written to stop.
#
# Most of what those two failures represented is now covered by
# `contrast-floor.test.ts` under `vitest`, which needs no browser. This runs
# the real page through axe, which is still the only thing that sees the
# composited result.
if [[ "$SCOPE" == "a11y" ]]; then
  if ! curl -sf -o /dev/null http://localhost:3000; then
    echo "a11y needs the dev server: run 'npm run dev' in frontend/ first" >&2
    exit 1
  fi
  run "a11y" env -C frontend E2E_BASE_URL=http://localhost:3000 \
    npx playwright test e2e/a11y.spec.ts --project=chromium
fi

echo
if [[ ${#FAILED[@]} -eq 0 ]]; then
  printf '\033[32m✓ gate passed — this is what CI will say\033[0m\n'
  exit 0
fi

printf '\033[31m✗ %d failed: %s\033[0m\n' "${#FAILED[@]}" "${FAILED[*]}"
exit 1
