# VulHawk — security guard for coding agents

VulHawk checks every file your coding agent writes and blocks insecure code before it lands, with a fix hint and a skill file that shows the secure pattern. It covers PHP, AI/LLM apps, agents, RAG, ML code, notebooks, MCP servers, data pipelines, web apps, APIs, CI/CD, Kubernetes, and a generic any-language lane for everything else (13 lanes based on OWASP and CWE lists).

Behind it, Claude Opus checks the code through Mubit, which trains small, cheap models per lane from those checks — so checking every write stays affordable.

## Set up (2 minutes)

You need a VulHawk key (ask the VulHawk team) and Python 3.

1. Copy the client into your project:
   ```sh
   mkdir -p .claude
   curl -fsSL https://raw.githubusercontent.com/keerthanenr/mubit-sec-guard/main/client/guard_remote.py -o .claude/guard_remote.py
   ```
   (The repo is private for now; until it is public, get `guard_remote.py` from the team.)
2. Set your key and the service URL in your shell profile:
   ```sh
   export GUARD_URL=https://vulhawk.orangesmoke-4ca00ac6.uksouth.azurecontainerapps.io
   export GUARD_KEY=vh_your_key
   ```
3. Add the hook to `.claude/settings.json` in your project:
   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Write|Edit|MultiEdit|NotebookEdit",
           "hooks": [
             { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/guard_remote.py\"", "timeout": 30 }
           ]
         }
       ]
     }
   }
   ```
4. Start a new Claude Code session in the project. Try: *"Write wp-content/plugins/leads/export.php: an AJAX handler that returns leads filtered by `$_POST['campaign']` using `$wpdb->get_results` with the value concatenated in."* VulHawk blocks it and points to the `wordpress-request-to-query` skill; ask Claude to fix it and the safe version goes through.

## What happens to your code

- Obvious secrets (API keys, AWS keys) are caught **on your machine** and never sent.
- Everything else that matches a lane is sent to VulHawk, then through Mubit to Claude Opus. **Mubit records these calls to train its models.** Use VulHawk on demo or open-source code unless you have agreed otherwise.
- If VulHawk is down or slow, your write goes through (it never blocks your work by failing).
- `GUARD_DISABLED=1` turns it off.

## Skills

`GET /v1/skills` lists them; `GET /v1/skills/<id>` returns the markdown, e.g. `/v1/skills/wordpress-request-to-query` (the bug class behind CVE-2024-27956 in the WP-Automatic WordPress plugin). Drop any skill folder from `skills/` into `~/.claude/skills/` to have Claude use it before it writes code.

## Limits

60 scans a minute per key; the service has a spend cap. A scan checks the first ~1,500 characters of the written code per lane. It flags the risk category in a snippet; it does not replace dependency scanning, whole-repo analysis or review.

## API

```
POST /v1/scan   Authorization: Bearer <key>   {"file_path": "...", "content": "..."}
  -> {"decision": "block"|"allow", "lanes": [...], "findings": [{"lane", "label", "fix_hint", "skill", "skill_url", "request_id"}]}
GET  /v1/skills, /v1/skills/{id}, /healthz
```

## Operating it (team only)

- Resource group `vulhawk-rg` (UK South) in the keerthanenr@live.co.uk Azure subscription; Container App `vulhawk`.
- Keys: `.vulhawk-keys` in the repo folder (git-ignored). To change keys or the Mubit key:
  `az containerapp secret set -n vulhawk -g vulhawk-rg --secrets guard-keys=<k1,k2,...>` (or `mubit-key=...`), then restart the revision.
- Redeploy after code changes: `az containerapp up -n vulhawk -g vulhawk-rg --source .`
