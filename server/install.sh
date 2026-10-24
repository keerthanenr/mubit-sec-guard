#!/bin/sh
# VulHawk installer. Run from your project folder:
#   curl -fsSL __URL__/install | sh -s -- YOUR_VULHAWK_KEY
set -eu
URL="__URL__"
KEY="${1:-${GUARD_KEY:-}}"

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
