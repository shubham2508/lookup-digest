#!/usr/bin/env bash
# Integration matrix (eval/integrate.py): all run days, the three honesty variants, the six customize prompts and
# the baseline on the last day, `digest simulate --fresh`, then `digest eval --customize-suite --baseline`.
#   scripts/integrate.sh [dev|heldout|tests/fixtures/mini] [--dry-run] [--keep-going]
# Exit: 0 ok · 3 blocked (a product stage not implemented yet, or no data) · 1 failed.
set -euo pipefail
cd "$(dirname "$0")/.."
world="${1:-dev}"
shift || true
exec uv run digest eval --matrix --world "$world" "$@"
