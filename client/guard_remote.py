#!/usr/bin/env python3
"""VulHawk client: a Claude Code PreToolUse hook that asks the hosted VulHawk guard. Python stdlib only.

Install from your project folder:  curl -fsSL <VulHawk URL>/install | sh -s -- <your key>

Or by hand: set GUARD_URL and GUARD_KEY (or put them in ~/.config/vulhawk/config), then add
to .claude/settings.json:

  {"hooks": {"PreToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit",
     "hooks": [{"type": "command", "command": "python3 \\"$CLAUDE_PROJECT_DIR/.claude/guard_remote.py\\"", "timeout": 30}]}]}}

Exit 2 blocks the write (reason on stderr). Obvious secrets are blocked locally and never
sent. If the guard can't be asked (network error, rejected or malformed key), the write goes
through with a visible warning. With no URL or key set it does nothing.
GUARD_DISABLED=1 turns it off.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
SECRET_PATTERNS = [
    re.compile(r"sk_live_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"""(?i)\b(?P<key>\w*(?:api_?key|secret)\w*)['"]?\s*(?:=>|=|:)\s*['"][^'"\s]{16,}['"]"""),
]
REFERENCE_KEY = re.compile(r"(?i)(?:id|name|arn|path|ref|env|var)$")


def has_secret(code):
    for pattern in SECRET_PATTERNS:
        for m in pattern.finditer(code):
            key = m.groupdict().get("key")
            if not (key and REFERENCE_KEY.search(key)):
                return True
    return False


def notebook_code(text):
    try:
        cells = json.loads(text).get("cells", [])
    except (ValueError, AttributeError):
        return text
    return "\n\n".join("".join(c["source"]) if isinstance(c.get("source"), list) else c.get("source", "")
                       for c in cells if c.get("cell_type") == "code")


def extract(tool, ti, path):
    if tool == "Write":
        content = ti.get("content") or ""
        return notebook_code(content) if path.lower().endswith(".ipynb") else content
    if tool == "NotebookEdit":
        return ti.get("new_source") or ""
    if tool == "Edit":
        return ti.get("new_string") or ""
    if tool == "MultiEdit":
        return "\n".join(e.get("new_string") or "" for e in ti.get("edits") or [])
    return ""


def settings():
    """GUARD_URL / GUARD_KEY from the environment, else from ~/.config/vulhawk/config (written by the installer)."""
    values = {}
    path = os.path.join(os.path.expanduser("~"), ".config", "vulhawk", "config")
    try:
        for line in open(path):
            k, _, v = line.strip().partition("=")
            values[k] = v
    except OSError:
        pass
    url = os.environ.get("GUARD_URL") or values.get("GUARD_URL", "")
    key = os.environ.get("GUARD_KEY") or values.get("GUARD_KEY", "")
    return url.strip().strip("'\"").rstrip("/"), key.strip().strip("'\"")


def bad_key_char(key):
    """The first character that can't go in an HTTP header (e.g. an en dash '–' from a copied
    install command whose '--' was auto-corrected), or None if the key is fine."""
    return next((c for c in key if not (c.isascii() and c.isprintable()) or c.isspace()), None)


def notice(message):
    """Let the write through but tell the user the guard didn't check it (never fail open silently)."""
    print(json.dumps({"systemMessage": f"⚠ VulHawk: {message}"}))
    print(f"VulHawk: {message}", file=sys.stderr)
    return 0


def main():
    url, key = settings()
    if os.environ.get("GUARD_DISABLED") == "1" or not url or not key:
        return 0
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    tool, ti = payload.get("tool_name"), payload.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    code = extract(tool, ti, path) if tool in TOOLS else ""
    if not path or not code.strip():
        return 0
    if has_secret(code):
        print(f"VulHawk: hardcoded_secret in {path} (caught locally, not sent). "
              "Load secrets from environment variables, not source code.", file=sys.stderr)
        return 2
    bad = bad_key_char(key)
    if bad is not None:
        return notice(f"your guard key contains {bad!r} (U+{ord(bad):04X}), so this write was NOT checked. "
                      "A copied install command probably had '--' turned into a dash. Re-run it typing the "
                      f"two hyphens yourself:  curl -fsSL {url}/install | sh -s -- YOUR_KEY")

    body = json.dumps({"file_path": path, "content": code[:200_000],
                       "session_id": str(payload.get("session_id") or "")[:128]}).encode()
    request = urllib.request.Request(f"{url}/v1/scan", data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.load(response)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return notice("the guard rejected your key, so this write was NOT checked. "
                          "Check GUARD_KEY in ~/.config/vulhawk/config.")
        return notice(f"the guard returned HTTP {e.code}, so this write was NOT checked.")
    except Exception as e:
        # Fail open (the guard being down never blocks work), but say so.
        return notice(f"couldn't reach the guard ({type(e).__name__}: {e}), so this write was NOT checked.")
    if result.get("decision") != "block":
        return 0
    for f in result.get("findings", []):
        line = f"VulHawk: {f['label']} in {path} ({f['lane']}). {f.get('fix_hint', '')}"
        if f.get("skill"):
            line += f" Follow the skill '{f['skill']}': {url}{f['skill_url']}"
        print(line, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
