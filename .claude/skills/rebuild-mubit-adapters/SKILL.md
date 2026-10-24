---
name: rebuild-mubit-adapters
description: Rebuild all 13 security-lane Mubit tasks and adapters in a new or empty Mubit account from this repo's datasets. Use when setting up a fresh Mubit project, moving to another Mubit account, or retraining every lane from scratch.
---

# Rebuild the Mubit adapters

Follow docs/REBUILD.md; it is the source of truth. Steps for a Claude Code session:

1. **Check prerequisites, never print secrets.** `.venv` exists with `openai` and `anthropic`; `.env` has `MUBIT_API_KEY`, `MUBIT_BASE_URL=https://api.mubit.ai/anthropic`, `MUBIT_MODEL=claude-opus-5-5`. Confirm the key line exists with `grep -c '^MUBIT_API_KEY=mbt_' .env`; never cat or echo `.env`.
2. **Ask the user to confirm console setup** (docs/REBUILD.md §1): Anthropic provider key valid, Mubit key created, "Live needs judged test cases" = 12, Silent test = 20%.
3. **Offline checks:** `.venv/bin/python -m unittest discover -s tests` must pass; `DRY_RUN=1 scripts/rebuild_all.sh` must finish with "No errors."
4. **Stop and ask before real calls.** Tell the user it is ~3,300 Opus calls, ~$5–6, billed to their Anthropic key through Mubit.
5. **One smoke call:** `.venv/bin/python smoke.py web_php`. Expect `label: none` and an `mreq_` request id. If not, stop and debug the route (docs/REBUILD.md §5 rule 1).
6. **Full send:** `scripts/rebuild_all.sh` (run in the background; ~15 min). Report per lane: rows recorded, holdout accuracy, false negatives, spend.
7. **Monitoring:** Mubit tasks move Collecting → Reviewing examples → Training → Testing over hours. Read the console with the user; the symptoms table in docs/REBUILD.md §6 says what to ask Mubit.

Do not edit any lane instruction in `config.py`: it would split the task (docs/REBUILD.md §5 rule 2). Do not send holdouts recorded. Do not add `temperature`.
