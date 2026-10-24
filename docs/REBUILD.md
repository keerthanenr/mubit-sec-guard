# Rebuilding the adapters in a new Mubit account

This repo holds everything needed to recreate the 13 security lanes as Mubit tasks and retrain their adapters from scratch: the fixed lane instructions (`config.py`), all labelled datasets (`data/`), and the scripts. Nothing from the old account is needed. A full rebuild is about 3,300 Opus calls and roughly $5–6 of provider spend.

## 1. Mubit account setup (console, ~10 min)

1. Sign up at app.mubit.ai and create a project.
2. **Provider keys** → add an **Anthropic** API key (the calls are billed to it). Check it shows *Valid*.
3. **Connect → Mubit key → Create key.** Copy it (shown once).
4. **Settings → Adapters → "Live needs N judged test cases"**: set **12** (default 20). With ~70–220 rows per lane, Mubit's held-back test sets are 12–25 cases; at 20, good adapters wait on evidence alone.
5. **Settings → Going live → Silent test**: set **20%** (default 10%).
6. Leave Training at "after 25 new examples", and Tests at 2% live checks with grading on.

## 2. Local setup (~2 min)

```sh
git clone https://github.com/keerthanenr/mubit-sec-guard.git && cd mubit-sec-guard
python3 -m venv .venv && .venv/bin/pip install openai anthropic
cp .env.example .env     # put the new Mubit key in MUBIT_API_KEY
.venv/bin/python -m unittest discover -s tests        # offline, all should pass
DRY_RUN=1 scripts/rebuild_all.sh                       # offline pipeline check
.venv/bin/python smoke.py web_php                      # ONE real call: expect label none + an mreq_ id
```

`.env` must contain:

```
MUBIT_API_KEY=mbt_...
MUBIT_BASE_URL=https://api.mubit.ai/anthropic
MUBIT_MODEL=claude-opus-5-5
```

## 3. Send everything (~15 min)

```sh
scripts/rebuild_all.sh
```

Per lane, in parallel: every training split (`seed`, `seed_extra`, `seed_extra2`, `seed_extra3`) with `--agree-only`, then the holdout unrecorded. Expected, from the original run:

- Opus agrees with our labels on ~95–100% of training rows; only agreeing rows are recorded.
- Holdout accuracy 93–100% per lane; 0–2 missed vulnerabilities per lane.

| Lane | Labels | seed | seed_extra | seed_extra2 | seed_extra3 | holdout | Recorded (max) |
|---|---|---|---|---|---|---|---|
| `web_php` | 6 | 60 | 60 | — | 72 | 24 | 192 |
| `ai_app` | 6 | 60 | 60 | 36 | — | 24 | 156 |
| `agent_app` | 7 | 70 | 70 | — | 84 | 28 | 224 |
| `rag_app` | 5 | 50 | 50 | 30 | — | 20 | 130 |
| `ml_code` | 6 | 60 | 60 | — | 72 | 24 | 192 |
| `data_science` | 6 | 60 | 60 | 36 | — | 24 | 156 |
| `mcp_server` | 7 | 70 | — | — | 49 | 28 | 119 |
| `data_pipeline` | 6 | 60 | — | — | — | 24 | 60 |
| `web_app` | 7 | 70 | — | — | — | 28 | 70 |
| `api_security` | 7 | 70 | — | — | — | 28 | 70 |
| `cicd` | 7 | 70 | — | — | — | 28 | 70 |
| `k8s_iac` | 7 | 70 | — | — | — | 28 | 70 |
| **Total** | | | | | | **308** | **1,509** |

## 4. Watch Mubit (hours)

Tasks → each lane appears as a task named from its instruction ("PHP security reviewer", "AI agent security reviewer", …). Stages: **Collecting → Reviewing examples → Training → Testing**, then Adapters shows a version.

- Grading took 30–60 min per batch; first training ran ~30 min after grading; a job took ~5 min. With 13 lanes, expect a few hours.
- An adapter that is **ready / candidate** has passed its quality check. It still needs **≥ 12 judged test cases** (the setting above), then **live traffic** for the silent test (≥ 50 paired comparisons over ≥ 10 sessions; 20% of calls shadowed, ≤ 100/day), then a 10% partial rollout (≥ 100 calls, 90% bar).
- Live traffic = ordinary recorded calls on that lane: the guard hook in use, or re-running a lane's seed split.

## 5. Rules that made it work (do not change these)

1. **Native Anthropic Messages on `https://api.mubit.ai/anthropic`.** OpenAI-format calls to `/anthropic/v1` were recorded but produced **0 kept examples**. (OpenAI needs credit on your OpenAI account; Gemini's OpenAI-compatible route rejects `metadata` and timed out.)
2. **Never edit a lane's instruction in `config.py` after its first send.** Mubit groups calls by byte-identical instruction + model; any edit creates a new task and starts over.
3. **One session per snippet** (`metadata.user_id`): Mubit holds back test cases by session.
4. **Shuffled send order** (`seed.py` does this): files are grouped by label, and unshuffled sends gave lopsided test sets.
5. **`--agree-only`**: each snippet is asked unrecorded first; the recorded call is sent only if Opus agrees with our label, so adapters never learn wrong answers.
6. **Holdouts are unrecorded** (`x-middleware-store: false`, `evaluate.py` does this), so they stay a fair test.
7. **Opus 5.5 at low effort** as teacher: no thinking, ~7 output tokens, ~2 s, ~$0.0016 a call. Do not send `temperature`: the API rejects it for these models.
8. **Label-only replies.** Every lane except `web_php` has one-line label definitions and "label only, one line" in its instruction. Adapters cannot match free-text answers at 95%.

## 6. What went wrong last time (and what to tell Mubit if it recurs)

| Symptom | What it was |
|---|---|
| v1 adapters 8–17%, always answering `none` | Too few rows (25–46), unshuffled sessions, Haiku teacher. Fixed by rules 4, 5, 7 and more data. |
| Tasks stuck in "Reviewing examples" for an hour+ | Mubit's grader stalled (status showed `embedding_service: unreachable`). Ask Mubit. |
| Training failed: "adapter job queue unavailable" | Mubit's job queue down; jobs did not retry. Ask Mubit to re-run them. |
| Candidate still says "below the 20-row evidence minimum" after lowering the setting | Old evaluations are not recomputed; ask Mubit to re-evaluate, or wait for the next version. |
| "Retrain needs 25 new rows" but nothing happens | Mubit also requires ~50% growth over the rows last trained on. |

## 7. Afterwards

- Use the guard: start Claude Code in this folder; the hook in `.claude/settings.json` checks writes under `demo-app/`. Live checks also feed the tasks.
- `report.py` shows common issues and spend per lane. `GUARD_BUDGET_USD` caps spend (default $50); delete `spend.json` for a fresh ledger in a new account.
- `python dashboard.py` charts the whole rebuild — seed vs holdout accuracy, spend and calls per lane, per-label recall — into `results/dashboard.html`. It only reads `results/` and `spend.json`, so it is free to re-run after every lane. `--publish` also writes `docs/dashboard.html`, the snapshot committed to the repo; `--model <dir>` scores a holdout run from a different teacher model.
