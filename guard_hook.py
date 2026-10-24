"""Claude Code PreToolUse hook: route a write to its lanes and block insecure code.

Lanes are picked by file suffix and imports (see config.LANES); a file can match
several lanes and is checked in each. Exit 0 = allow, exit 2 = block (reason on
stderr). Fails open on errors.
"""
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import classifier  # noqa: E402
import config  # noqa: E402
import local_checks  # noqa: E402
import spend  # noqa: E402

TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
BLOCK_CAP = 3


def _notebook_code(text):
    """Join the code cells of a .ipynb file; fall back to the raw text."""
    try:
        cells = json.loads(text).get("cells", [])
    except (ValueError, AttributeError):
        return text
    return "\n\n".join("".join(c.get("source", "")) if isinstance(c.get("source"), list)
                        else c.get("source", "") for c in cells if c.get("cell_type") == "code")


def extract_code(tool, tool_input, file_path=""):
    if tool == "Write":
        content = tool_input.get("content") or ""
        return _notebook_code(content) if file_path.lower().endswith(".ipynb") else content
    if tool == "NotebookEdit":
        return tool_input.get("new_source") or ""
    if tool == "Edit":
        return tool_input.get("new_string") or ""
    if tool == "MultiEdit":
        return "\n".join(e.get("new_string") or "" for e in tool_input.get("edits") or [])
    return ""


def _imports(code, modules):
    names = "|".join(re.escape(m) for m in modules)
    # Python / Java imports, then JS: require('x'), import ... from 'x', import 'x'.
    pattern = (r"^\s*(?:import|from)\s+(?:" + names + r")\w*\b"
               r"|\brequire\(\s*['\"](?:" + names + r")['\"/]"
               r"|^\s*import\b[^;\n]*['\"](?:" + names + r")['\"/]")
    return re.search(pattern, code, re.M) is not None


def route(file_path, code, read_existing=True):
    """The lanes this write belongs to (possibly several), or [] to ignore it.

    read_existing=False routes on the submitted code only (the hosted API must
    never read its own disk based on a client-supplied path).
    """
    if not file_path or not Path(file_path).resolve().is_relative_to(config.scope_dir()):
        return []
    lower = file_path.lower()
    # An Edit may not include the imports, so also look at the file being edited.
    existing = ""
    if read_existing:
        try:
            existing = Path(file_path).read_text(errors="ignore")
            if lower.endswith(".ipynb"):
                existing = _notebook_code(existing)
        except OSError:
            existing = ""
    lanes = []
    for lane in config.LANES.values():
        if lane.fallback:
            continue
        if lower.endswith(lane.always_suffixes or ("\0",)):
            lanes.append(lane.name)
        elif lower.endswith(lane.suffixes or ("\0",)) and _lane_matches(lane, lower, code, existing):
            lanes.append(lane.name)
    if not lanes:
        lanes = [lane.name for lane in config.LANES.values()
                 if lane.fallback and lower.endswith(lane.suffixes or ("\0",))]
    return lanes


def _lane_matches(lane, lower_path, code, existing):
    """A suffix match also needs an import, a path marker or all content markers, if the lane names any."""
    if not (lane.modules or lane.path_markers or lane.content_markers):
        return True
    text = code + "\n" + existing
    return bool(
        (lane.modules and (_imports(code, lane.modules) or _imports(existing, lane.modules)))
        or any(m in lower_path for m in lane.path_markers)
        or (lane.content_markers and all(m in text for m in lane.content_markers))
    )


def _load_state(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def log_finding(lane, file_path, label, request_id, decision, snippet):
    entry = {
        "id": uuid.uuid4().hex[:12],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lane": lane,
        "file": file_path,
        "label": label,
        "request_id": request_id,
        "decision": decision,
        "snippet": snippet,
    }
    with open(config.state_dir() / "findings.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def classify_lanes(lanes, code, session):
    """Return [(lane, label, request_id)] for each lane. Secrets are caught locally first."""
    label, redacted = local_checks.check(code)
    if label is not None:
        return [(lanes[0], label, None)], redacted
    results = []
    for lane in lanes:
        try:
            lane_label, request_id = classifier.classify(redacted, session, lane)
        except spend.BudgetExceeded:
            lane_label, request_id = "budget_exceeded", None
        except Exception:
            lane_label, request_id = "error", None
        results.append((lane, lane_label, request_id))
    return results, redacted


def main():
    if config.disabled():
        return 0
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0

    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if tool not in TOOLS:
        return 0
    code = extract_code(tool, tool_input, file_path)
    lanes = route(file_path, code)
    if not lanes or not code.strip():
        return 0

    before = spend.snapshot()
    results, redacted = classify_lanes(
        lanes, code, f"scan-{payload.get('session_id') or 'unknown'}")
    after_usd = spend.load()["total_usd"]
    call_usd = after_usd - before["total_usd"]
    print(f"guard: scan cost ~${call_usd:.6f} ({len(lanes)} lane(s)); total est. ${after_usd:.4f}",
          file=sys.stderr)
    findings = [(lane, label, rid) for lane, label, rid in results
                if label not in ("none", classifier.UNPARSEABLE, "error", "budget_exceeded")]
    for lane, label, rid in results:
        if (lane, label, rid) not in findings:
            decision = "error" if label in ("error", "budget_exceeded") else "allow"
            log_finding(lane, file_path, label, rid, decision, redacted)
    if not findings:
        return 0

    state_path = config.state_dir() / ".guard_state.json"
    state = _load_state(state_path)
    blocks = state.get(file_path, 0)
    if blocks >= BLOCK_CAP:
        for lane, label, rid in findings:
            log_finding(lane, file_path, label, rid, "allowed_by_cap", redacted)
        return 0
    state[file_path] = blocks + 1
    state_path.write_text(json.dumps(state, indent=2))
    for lane, label, rid in findings:
        log_finding(lane, file_path, label, rid, "block", redacted)
        hint = config.LANES[lane].fix_hints.get(label, config.SECRET_HINT)
        print(f"guard: {label} in {file_path} ({lane}). {hint}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
