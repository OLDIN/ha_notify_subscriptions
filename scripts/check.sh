#!/usr/bin/env bash
# Run locally what CI runs: pre-commit (ruff, whitespace, yaml), mypy, pytest and hassfest.
# HACS validation is not here: it checks the GitHub repository itself (description, topics).
#
#   scripts/check.sh            — everything
#   scripts/check.sh hassfest   — only hassfest
set -euo pipefail
cd "$(dirname "$0")/.."
VENV="${VENV:-$PWD/.venv-ha}/bin"
INTEGRATION="$PWD/custom_components/notify_subscriptions"

run_hassfest() {
  # hassfest lives in the Home Assistant core repo; use the release the tests run on
  local version core="$PWD/.hassfest-core"
  version=$("$VENV/python" -c "import homeassistant.const as c; print(c.__version__)")
  if [ ! -f "$core/.version" ] || [ "$(cat "$core/.version")" != "$version" ]; then
    rm -rf "$core"
    git clone -q --depth 1 --branch "$version" https://github.com/home-assistant/core.git "$core"
    echo "$version" > "$core/.version"
  fi
  (cd "$core" && "$VENV/python" -m script.hassfest --integration-path "$INTEGRATION")
}

if [ "${1:-all}" = "hassfest" ]; then
  run_hassfest
  exit
fi

PATH="$VENV:$PATH" "$VENV/pre-commit" run --all-files
run_hassfest
echo "✅ all local checks passed"
