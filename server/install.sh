#!/bin/sh
# VulHawk installer. Run from your project folder:
#   curl -fsSL __URL__/install | sh -s -- YOUR_VULHAWK_KEY
set -eu
LC_ALL=C  # byte-wise pattern matching for the key check below
URL="__URL__"
# Chat apps and docs often auto-correct "--" into an en or em dash, which sh then passes as
# the first argument. Skip it so the real key is used.
case "${1:-}" in "–"|"—"|"-") shift ;; esac
KEY="${1:-${GUARD_KEY:-}}"
# A key is plain ASCII letters, digits, '.', '_' or '-'; anything else breaks every request.
case "$KEY" in
  *[!A-Za-z0-9._-]*)
    echo "That key has a character a VulHawk key can't contain (often a dash or quote from copy-paste)."
    echo "Re-run, typing the two hyphens yourself:  curl -fsSL $URL/install | sh -s -- YOUR_KEY"
    exit 1 ;;
esac

command -v python3 >/dev/null 2>&1 || { echo "VulHawk needs python3."; exit 1; }
mkdir -p .claude
curl -fsSL "$URL/client/guard_remote.py" -o .claude/guard_remote.py

python3 - <<'PY'
import json, os
path = ".claude/settings.json"
settings = json.load(open(path)) if os.path.exists(path) else {}
entries = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
command = 'python3 "$CLAUDE_PROJECT_DIR/.claude/guard_remote.py"'
if not any(h.get("command") == command for e in entries for h in e.get("hooks", [])):
    entries.append({"matcher": "Write|Edit|MultiEdit|NotebookEdit",
                    "hooks": [{"type": "command", "command": command, "timeout": 30}]})
with open(path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PY

if [ -n "$KEY" ]; then
  mkdir -p "$HOME/.config/vulhawk"
  ( umask 077; printf 'GUARD_URL=%s\nGUARD_KEY=%s\n' "$URL" "$KEY" > "$HOME/.config/vulhawk/config" )
  echo "VulHawk key saved to ~/.config/vulhawk/config"
else
  echo "No key given. Re-run with your key:  curl -fsSL $URL/install | sh -s -- YOUR_KEY"
fi
echo "VulHawk installed in $(pwd)/.claude. Start a new Claude Code session here; every file write is now checked."
echo "Turn it off any time with: export GUARD_DISABLED=1"
