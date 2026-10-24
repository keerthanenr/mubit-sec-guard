"""VulHawk: hosted security guard API.

POST /v1/scan          check one file write (Bearer guard key required)
GET  /v1/skills        list skill ids
GET  /v1/skills/{id}   a skill's markdown (public)
GET  /healthz          liveness

Env: MUBIT_API_KEY, MUBIT_BASE_URL, MUBIT_MODEL (as for the hook), GUARD_API_KEYS
(comma-separated keys allowed to scan), GUARD_RATE_PER_MIN (default 60 per key),
GUARD_BUDGET_USD (spend cap), GUARD_STATE_DIR (where spend.json lives).
"""
import hashlib
import os
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GUARD_SCOPE_DIR", "/")  # clients send their own paths; scope is theirs

import classifier  # noqa: E402
import config  # noqa: E402
import guard_hook  # noqa: E402

from server.skills import list_skills, read_skill, skill_for  # noqa: E402

MAX_CONTENT_CHARS = 200_000
app = FastAPI(title="VulHawk security guard", version="1.0")
_calls = defaultdict(deque)


class ScanRequest(BaseModel):
    file_path: str = Field(min_length=1, max_length=1024)
    content: str = Field(max_length=MAX_CONTENT_CHARS)
    session_id: str | None = Field(default=None, max_length=128)


def _authorize(authorization):
    keys = {k.strip() for k in os.environ.get("GUARD_API_KEYS", "").split(",") if k.strip()}
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not keys or token not in keys:
        raise HTTPException(status_code=401, detail="missing or unknown guard key")
    limit = int(os.environ.get("GUARD_RATE_PER_MIN", "60"))
    window, now = _calls[token], time.monotonic()
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(status_code=429, detail="rate limit: try again in a minute")
    window.append(now)
    return hashlib.sha256(token.encode()).hexdigest()[:10]  # caller id for sessions, never the key


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "VulHawk", "lanes": len(config.LANES), "model": config.model()}


@app.get("/v1/skills")
def skills_index():
    return {"skills": list_skills()}


@app.get("/v1/skills/{skill_id}", response_class=PlainTextResponse)
def skill(skill_id: str):
    text = read_skill(skill_id)
    if text is None:
        raise HTTPException(status_code=404, detail="no such skill")
    return text


@app.post("/v1/scan")
def scan(req: ScanRequest, authorization: str | None = Header(default=None)):
    caller = _authorize(authorization)
    lanes = guard_hook.route(req.file_path, req.content, read_existing=False)
    if not lanes or not req.content.strip():
        return {"decision": "allow", "lanes": [], "findings": [], "errors": []}

    session = f"api-{caller}-{req.session_id or 'none'}"
    results, _ = guard_hook.classify_lanes(lanes, req.content, session)
    findings, errors = [], []
    for lane, label, request_id in results:
        if label in ("none", classifier.UNPARSEABLE):
            continue
        if label in ("error", "budget_exceeded"):
            errors.append({"lane": lane, "error": label})
            continue
        skill_id = skill_for(lane, label, req.content)
        findings.append({
            "lane": lane,
            "label": label,
            "fix_hint": config.LANES[lane].fix_hints.get(label, config.SECRET_HINT),
            "skill": skill_id,
            "skill_url": f"/v1/skills/{skill_id}" if skill_id else None,
            "request_id": request_id,
        })
    return {"decision": "block" if findings else "allow", "lanes": lanes,
            "findings": findings, "errors": errors}
