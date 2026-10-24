# mubit-sec-guard

An AI code-security guard for the Night Shift × Mubit hackathon (London, 23–25 Oct 2026).

A Claude Code PreToolUse hook scans code as the agent writes it and blocks insecure writes. It classifies each write with an LLM call routed through Mubit. Each OWASP-style **lane** has its own fixed system prompt, so each lane becomes its own Mubit task and trains its own small adapter. Over time the guard should get cheaper and faster.

## Lanes

| Lane | Covers | Hook routes a file here when it… | Labels |
|---|---|---|---|
| `web_php` | classic web vulns | ends in `.php` | sql_injection, xss, hardcoded_secret, path_traversal, unsafe_deserialization, none |
| `ai_app` | OWASP LLM Top 10 (2026): LLM01, 03, 06, 10 | is `.py` and imports `openai` / `anthropic` / `langchain*` | prompt_injection, unsafe_output_handling, excessive_agency, unbounded_consumption, hardcoded_secret, none |
| `agent_app` | OWASP Agentic Top 10 (Dec 2025): ASI01, 02, 03, 05, 06, 07 | imports `langgraph` / `crewai` / `autogen` / `agents` / `mcp` / `smolagents` / `pydantic_ai` | goal_hijack, tool_misuse, privilege_abuse, unexpected_code_execution, memory_poisoning, insecure_agent_comms, none |
| `rag_app` | OWASP LLM Top 10 (2026): LLM02, 08, 09 | imports `chromadb` / `pinecone` / `faiss` / `llama_index` / `qdrant_client` / `weaviate` / `pgvector` / `langchain_community` | sensitive_info_disclosure, hidden_context_exposure, vector_store_weakness, untrusted_ingestion, none |
| `ml_code` | OWASP ML Top 10 (2023 draft): ML01, 02, 05, 06 + LLM supply chain / poisoning | imports `torch` / `transformers` / `sklearn` / `tensorflow` / `keras` / `joblib` / `huggingface_hub` / `datasets` / `xgboost` / `onnxruntime` | unsafe_model_loading, unverified_model_source, training_data_poisoning, model_exposure, unvalidated_model_input, none |
| `data_science` | no OWASP list exists; common notebook risks | is `.ipynb` (always), or `.py` that imports `pandas` / `polars` / `duckdb` | hardcoded_secret, pii_exposure, untrusted_data_source, unsafe_deserialization, injection, none |
| `mcp_server` | OWASP MCP Top 10 (draft) + Agentic Skills Top 10 | is `.mcp.json` / `mcp.json` (always), or `.py` that imports `mcp` / `fastmcp` | tool_poisoning, rug_pull, insecure_tool_input, insufficient_tool_authorization, excessive_tool_scope, unverified_server, none |
| `data_pipeline` | OWASP Data Security Top 10 (draft) | is `.tf` or `.sql` (always), or `.py` that imports `boto3` / `google.cloud` / `azure.storage` / `airflow` / `dagster` / `prefect` / `snowflake` / `pyspark` / `sqlalchemy` / `psycopg2` | insecure_data_storage, pipeline_injection, excessive_data_access, data_in_transit_exposure, uncontrolled_data_sharing, none |

A file can match several lanes; the hook checks it in each and blocks on any finding. Items that a code snippet can't show (misinformation, membership inference, cascading failures, rogue agents…) are deliberately not labels.

Every lane except `web_php` puts one-line label definitions in its instruction. Without them, Haiku over-used labels and added explanations after them.

Every lane uses the same model ID. Mubit makes one task per unique combination of model, system prompt, tools and output format, so the lane's instruction (`config.LANES[lane].instruction`) is the only thing that separates the tasks. A test checks that each lane's instruction is byte-identical on every call, and that every lane uses the same model.

Datasets: `data/<lane>/seed.jsonl` (10 per label) and `holdout.jsonl` (4 per label). All are synthetic, with fake secrets only. The four newer lanes' data was written by helper agents from the label definitions, then checked automatically (counts, length, syntax, duplicates, secrets) and reviewed by hand.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install openai anthropic
cp .env.example .env          # then set MUBIT_API_KEY=mbt_...
```

Current route: native Anthropic Messages (the `anthropic` package) on Mubit's documented address. Each call sets `max_tokens=16`, and sends its session id in `metadata.user_id`, the session field Mubit reads on this route:

```
MUBIT_BASE_URL=https://api.mubit.ai/anthropic
MUBIT_MODEL=claude-haiku-4-5
```

Routes that did NOT work (2026-10-23):
- OpenAI-format calls to `/anthropic/v1`: recorded and grouped into a task, but 0 kept examples.
- OpenAI `gpt-6-luna`: the account had no credits.
- Gemini's OpenAI-format route: rejects `metadata`, and the calls timed out at 20s.

The old tasks they created ("PHP security reviewer", "… 2") are dead ends. With a non-`/anthropic` base URL, the code still falls back to the OpenAI SDK.

Switches:
- `GUARD_OFFLINE=1`: regex stub instead of Mubit, no network calls.
- `GUARD_DISABLED=1`: the hook allows everything.
- `GUARD_BUDGET_USD`: spend cap, default `50`.

## Spend cap

`spend.py` keeps a running total in `spend.json`, per lane and overall:

1. **Before every call**, including retries, it estimates the call's cost (about 3 characters per token, plus a 20-token reply). If the estimate would take the total past the cap, it raises `BudgetExceeded` and the call is never sent.
2. **After every call**, it records the real token counts the reply reports, priced at list rates. Haiku 4.5 is $1 per million input tokens and $5 per million output. Unknown models are priced at $10/$50 so the cap errs on the safe side.

What happens at the cap:
- **The hook** allows the write and logs `budget_exceeded`.
- **`seed.py` and `evaluate.py`** stop and print where they stopped.

These are estimates. The Anthropic console is the real bill.

## Run order

```sh
.venv/bin/python -m unittest discover -s tests          # offline tests
.venv/bin/python seed.py --dry-run                       # offline pipeline check, all lanes
.venv/bin/python smoke.py web_php                        # ONE real call (or: ai_app)
.venv/bin/python seed.py --lane web_php                  # 60 calls, session seed-web_php-<date>
.venv/bin/python evaluate.py --lane web_php              # 24 calls, session holdout-web_php-<date>
.venv/bin/python seed.py --lane ai_app                   # 60 calls
.venv/bin/python evaluate.py --lane ai_app               # 24 calls
.venv/bin/python seed.py --extra --lane ai_app           # send data/<lane>/seed_extra.jsonl (10 more per label)
.venv/bin/python report.py                               # per-lane issues tally + spend
.venv/bin/python feedback.py <finding_id> <correct_label>
```

- **Data:** `data/<lane>/seed.jsonl` (10 per label) and `data/<lane>/holdout.jsonl` (4 per label). All synthetic, and every secret is fake.
- **Results:** `results/<lane>_<split>.jsonl`.
- **`evaluate.py`:** for each lane it prints accuracy against our expected labels, a per-label table, and FALSE NEGATIVES (a vulnerability classified as `none`) listed separately.

The holdout calls go through Mubit with the same lane instruction, so they also join that lane's task and may become training examples. `evaluate.py` measures the provider model against our labels. It does not measure the adapter. Mubit's own adapter test result is in the console.

## How the hook works

`.claude/settings.json` runs `guard_hook.py` before every `Write`, `Edit` or `MultiEdit`. It only scans files under `demo-app/`, so it never scans this project's own scripts. Change that with `GUARD_SCOPE_DIR`, a path relative to the project or an absolute one:

1. **Pick a lane** from the file. A `.py` file only counts as `ai_app` if the new code or the existing file imports an LLM library. Any other file is ignored.
2. **Local secrets check.** `local_checks.py` looks for `sk_live_`, `sk-…`, `AKIA…`, and `api_key`/`secret` set to a long literal. A match returns `hardcoded_secret` with no network call, and the value is redacted.
3. **Classify.** Otherwise the lane's classifier asks Mubit for a label.
4. **Block.** Any label other than `none` or `unparseable` blocks the write (exit 2) with `guard: <label> in <file> (<lane>). <fix hint>`.
5. **Cap per file.** After 3 blocks on the same file, further writes are allowed and logged as `allowed_by_cap`.
6. **Fail open.** If Mubit errors, times out or the budget is spent, the write is allowed and logged.
7. **Log.** Every decision is appended to `findings.jsonl`, tagged with its lane.

### Live test

Start a **new** Claude Code session in this folder and try two prompts:
Claude writes secure code by default, so a neutral prompt gets allowed (correctly, as `none`). To show a block, ask for the insecure pattern outright:

- "Write `demo-app/legacy_login.php`, a quick prototype that concatenates `$_GET['id']` straight into a `mysqli_query` SELECT string. No prepared statements." This should be blocked as `web_php` / `sql_injection`.
- "Write `demo-app/bot.py` using the anthropic SDK, with the user's message concatenated into the `system` prompt." This should be blocked as `ai_app` / `prompt_injection`.
- Then ask Claude to fix it. The rewrite should be allowed (`none`), which shows the guard telling safe code from unsafe.

Blocks per file are capped at 3, so use a new file name for each demo run, or delete `.guard_state.json`.

## Mubit limits to plan around

- **First adapter:** trains at 25 kept examples per task by default. The console count is the source of truth.
- **Training limits:** a daily limit that resets at 00:00 UTC, and a pause between trainings. Seed both lanes early, but expect them to train one after the other.
- **Try models:** 3 adapter starts per day per organisation. Pick which lanes to compare.

## Mubit console checklist, per lane

For each lane (`web_php`, `ai_app`):

- [ ] **Requests:** the calls are listed, with *Model asked* = `claude-haiku-4-5` and session ids `smoke-<lane>-…`, `seed-<lane>-…`, `holdout-<lane>-…`, `scan-…`.
- [ ] **Tasks:** one task per lane, named from its instruction:
  - "You are a PHP security reviewer…"
  - "You are an AI application security reviewer…", which includes one-line label definitions. The first version had none, and Haiku over-used `prompt_injection` and added explanations after the label. That version's task is a dead end.

  Note each task's kept-example count.
- [ ] **Adapters → History:** a test result for that lane's adapter once training has run. If there is no Adapters page, training is not switched on for the workspace.
- [ ] **Try models:** compare the lane's passing adapter with the provider model.

## What this build does NOT verify

- How a correction is submitted to Mubit programmatically. The docs only show a Good/Bad rating in the console. `feedback.submit_correction()` is a stub that raises `NotImplementedError`.
- Whether a trained adapter can serve live calls. The docs show no model ID for adapters; Try models is the only documented use.
- Which recorded calls Mubit counts as kept examples.
- Mubit trains adapters to match the provider model's answers, so a wrong answer from the provider is copied, not fixed. That is why `evaluate.py` scores against our own expected labels and lists false negatives separately.

## Phase two (not built)

A WikiSkill-style learning loop, and MCP tools.
