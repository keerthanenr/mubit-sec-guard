"""Local spend ledger with a hard cap (GUARD_BUDGET_USD, default $50).

Costs are estimates from the token counts each reply reports, at list prices.
The provider console is the real bill.
"""
import fcntl
import json
import os

import config

# USD per million tokens (input, output).
PRICES_PER_MTOK = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
# Unknown models are priced high on purpose, so the cap errs on the safe side.
FALLBACK_PRICE = (10.00, 50.00)
# Pre-call guess: ~3 chars per token plus overhead, and a short label reply.
EST_OUTPUT_TOKENS = 20


class BudgetExceeded(Exception):
    pass


def _path():
    return config.state_dir() / "spend.json"


def load():
    try:
        return json.loads(_path().read_text())
    except (OSError, ValueError):
        return {"total_usd": 0.0, "lanes": {}}


def cost(input_tokens, output_tokens, model=None):
    price_in, price_out = PRICES_PER_MTOK.get(model or config.model(), FALLBACK_PRICE)
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def estimate(messages):
    chars = sum(len(m["content"]) for m in messages)
    out = config.reply_tokens() if config.always_thinks() else EST_OUTPUT_TOKENS
    return cost(chars // 3 + 20, out)


def check(estimated_usd):
    total = load()["total_usd"]
    if total + estimated_usd > config.budget_usd():
        raise BudgetExceeded(f"spend ${total:.4f} + next call ~${estimated_usd:.4f} "
                             f"would pass the ${config.budget_usd():.2f} cap")


def record(lane, input_tokens, output_tokens):
    usd = cost(input_tokens, output_tokens)
    # Several lanes may be seeded in parallel: lock, then write atomically.
    with open(_path().with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = load()
        entry = data["lanes"].setdefault(
            lane, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "usd": 0.0})
        entry["calls"] += 1
        entry["input_tokens"] += input_tokens
        entry["output_tokens"] += output_tokens
        entry["usd"] += usd
        data["total_usd"] += usd
        tmp = _path().with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, _path())
    return usd


def snapshot() -> dict:
    """Capture ledger state before a run so run_summary() can compute the delta."""
    data = load()
    return {
        "total_usd": data["total_usd"],
        "lanes": {lane: dict(stats) for lane, stats in data["lanes"].items()},
    }


def run_summary(before: dict) -> None:
    """Print tokens and cost for this run (delta vs before) and the all-time total."""
    after = load()
    run_calls = run_in = run_out = 0.0
    run_usd = after["total_usd"] - before["total_usd"]

    rows = []
    for lane, cur in after["lanes"].items():
        prev = before["lanes"].get(lane, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "usd": 0.0})
        d_calls = cur["calls"] - prev["calls"]
        d_in = cur["input_tokens"] - prev["input_tokens"]
        d_out = cur["output_tokens"] - prev["output_tokens"]
        d_usd = cur["usd"] - prev["usd"]
        if d_calls:
            rows.append((lane, d_calls, d_in, d_out, d_usd))
            run_calls += d_calls
            run_in += d_in
            run_out += d_out

    print("\n=== Run summary ===")
    for lane, calls, in_tok, out_tok, usd in rows:
        print(f"  {lane:<14}{calls:>4} calls  {in_tok:>7,} in / {out_tok:>6,} out tokens  ${usd:.4f}")
    sep = "─" * 61
    print(f"  {sep}")
    print(f"  {'this run':<14}{int(run_calls):>4} calls  {int(run_in):>7,} in / {int(run_out):>6,} out tokens  ${run_usd:.4f}")
    print(f"  {'all-time':<14}{'':>4}       {'':>7}    {'':>6}              ${after['total_usd']:.4f}"
          f" of ${config.budget_usd():.2f} cap")
