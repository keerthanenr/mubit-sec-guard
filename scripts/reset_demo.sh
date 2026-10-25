#!/usr/bin/env bash
# Reset demo-app/ and the guard's state before recording a demo take.
#
#   scripts/reset_demo.sh          block mode (default)
#   scripts/reset_demo.sh ask      or: warn
#
# Removes the files the demo prompts create, clears the per-file block counts,
# moves findings.jsonl aside (kept as findings.<timestamp>.jsonl) and sets
# GUARD_MODE in .env.
set -euo pipefail
cd "$(dirname "$0")/.."

mode="${1:-block}"
case "$mode" in block|warn|ask) ;; *) echo "mode must be block, warn or ask"; exit 1 ;; esac

rm -f demo-app/user_lookup.php demo-app/support_bot.py demo-app/ping_tool.go \
      demo-app/bot.py demo-app/calc.js demo-app/report.py demo-app/thumb.py
rm -f .guard_state.json
[ -s findings.jsonl ] && mv findings.jsonl "findings.$(date +%Y%m%d-%H%M%S).jsonl"

if grep -q '^GUARD_MODE=' .env; then
  sed -i.bak "s/^GUARD_MODE=.*/GUARD_MODE=$mode/" .env && rm -f .env.bak
else
  echo "GUARD_MODE=$mode" >> .env
fi
echo "demo reset: GUARD_MODE=$mode"
ls demo-app
