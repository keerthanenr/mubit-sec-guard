#!/usr/bin/env bash
# Rebuild every lane's Mubit task from the committed datasets, in a (new) Mubit account.
#
#   scripts/rebuild_all.sh             real run: Opus 5.5 teacher, agree-only, holdouts unrecorded
#   DRY_RUN=1 scripts/rebuild_all.sh   offline: regex stub, no network, nothing sent
#   LANES="web_php ml_code" scripts/rebuild_all.sh   only some lanes
#
# Per lane, in order: every training split that exists (seed, seed_extra, seed_extra2,
# seed_extra3) with --agree-only, then the unrecorded holdout. Lanes run in parallel.
# Logs: results/rebuild/<lane>.log. Spend is capped by GUARD_BUDGET_USD (default 50).
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
[ -x "$PY" ] || { echo "No .venv. Run: python3 -m venv .venv && .venv/bin/pip install openai anthropic"; exit 1; }
[ -f .env ] || [ "${DRY_RUN:-}" = "1" ] || { echo "No .env. Copy .env.example to .env and add your Mubit key."; exit 1; }

export MUBIT_MODEL="${MUBIT_MODEL:-claude-opus-5-5}"
DRY=""; [ "${DRY_RUN:-}" = "1" ] && DRY="--dry-run"
ALL_LANES=$($PY -c "import config; print(' '.join(config.LANES))")
LANES="${LANES:-$ALL_LANES}"
mkdir -p results/rebuild

run_lane() {
  local lane=$1 log=results/rebuild/$1.log
  : > "$log"
  for split in seed seed_extra seed_extra2 seed_extra3; do
    [ -f "data/$lane/$split.jsonl" ] || continue
    $PY seed.py --lane "$lane" --split "$split" --agree-only $DRY >> "$log" 2>&1
  done
  $PY evaluate.py --lane "$lane" $DRY >> "$log" 2>&1
}

echo "Model: $MUBIT_MODEL ${DRY:+(dry run)}"
echo "Lanes: $LANES"
for lane in $LANES; do run_lane "$lane" & done
wait

echo
echo "== Recorded per split (agree-only):"
grep -h "matched expected" results/rebuild/*.log || true
echo
echo "== Holdout (unrecorded):"
grep -h -E "^### |FALSE NEGATIVES" results/rebuild/*.log || true
echo
grep -l " error:" results/rebuild/*.log 2>/dev/null && echo "^ logs with errors, check them" || echo "No errors."
$PY -c "import seed; seed.print_spend()"
