#!/usr/bin/env bash
# Run locally what CI runs. HACS validation is not here: it checks the GitHub repository itself
# (description, topics).
#
#   scripts/check.sh            — everything: pre-commit hooks + mypy + pytest + card tests + hassfest
#   scripts/check.sh push       — mypy + pytest + card tests + hassfest (the pre-push git hook runs this)
#   scripts/check.sh hassfest   — only hassfest
set -euo pipefail
cd "$(dirname "$0")/.."
VENV="${VENV:-$PWD/.venv-ha}/bin"
INTEGRATION="$PWD/custom_components/notify_subscriptions"

if [ ! -x "$VENV/python" ]; then
  echo "No virtualenv at $VENV. Run scripts/setup_dev_env.sh first (or set VENV=...)." >&2
  exit 1
fi

run_hassfest() {
  # hassfest lives in the Home Assistant core repo; use the release the tests run on
  local version core="$PWD/.hassfest-core"
  version=$("$VENV/python" -c "import homeassistant.const as c; print(c.__version__)")
  if [ ! -f "$core/.version" ] || [ "$(cat "$core/.version")" != "$version" ]; then
    rm -rf "$core"
    git clone -q --depth 1 --branch "$version" https://github.com/home-assistant/core.git "$core" 2>/dev/null
    echo "$version" > "$core/.version"
  fi
  echo "── hassfest (HA $version)"
  (cd "$core" && "$VENV/python" -m script.hassfest --integration-path "$INTEGRATION" | tail -3)
}

run_push_checks() {
  echo "── mypy"
  "$VENV/mypy" custom_components/notify_subscriptions
  echo "── pytest"
  "$VENV/pytest" -q
  echo "── card (vitest + snapshots)"
  if [ -d node_modules ]; then
    npm test --silent
  else
    echo "node_modules is missing: run npm ci to test the card" >&2
    exit 1
  fi
  run_hassfest
}

case "${1:-all}" in
  hassfest) run_hassfest ;;
  push) run_push_checks ;;
  all)
    "$VENV/pre-commit" run --all-files
    run_push_checks
    echo "✅ all local checks passed"
    ;;
  *) echo "usage: $0 [all|push|hassfest]"; exit 1 ;;
esac
