"""Send data/<lane>/seed.jsonl through classify. Use --dry-run to stay offline."""
import argparse
import json
import os
import random
from datetime import date

import config
import spend


def data_path(lane, split):
    return config.ROOT / "data" / lane / f"{split}.jsonl"


def results_path(lane, split):
    # Dry runs never overwrite the record of a real run.
    folder = "results/dry_run" if config.offline() else "results"
    if not config.offline() and config.model() != "claude-haiku-4-5":
        folder += f"/{config.model()}"  # keep each teacher model's results apart
    return config.ROOT / folder / f"{lane}_{split}.jsonl"


def run_batch(lane, split, store=True, agree_only=False):
    """Classify every row of data/<lane>/<split>.jsonl. Stops early at the budget cap.

    Calls go straight to classify(), not through the hook's local secrets
    pre-filter, so hardcoded_secret examples reach Mubit.

    agree_only: ask unrecorded first, and send the recorded call only when the
    provider's label matches ours. Mubit trains the adapter to copy recorded
    answers, so this keeps wrong labels out of its training rows and test cases.
    """
    import classifier

    session_id = f"{split}-{lane}-{date.today().isoformat()}"
    rows = [json.loads(line) for line in open(data_path(lane, split)) if line.strip()]
    # Files are grouped by label. Mubit holds back whole sessions as test cases, so send in a
    # fixed shuffled order to spread every label across its training and test sets.
    random.Random(f"{lane}-{split}").shuffle(rows)
    out_path = results_path(lane, split)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    spent_before = spend.load()["lanes"].get(lane, {}).get("usd", 0.0)
    stored = "recorded by Mubit" if store else "NOT recorded (x-middleware-store: false)"
    if agree_only:
        stored += ", only where the provider agrees with our label"
    print(f"== {lane} / {split}: {len(rows)} snippets, sessions {session_id}-NNN, {stored}")
    results = []
    with open(out_path, "w") as out:
        for i, row in enumerate(rows, 1):
            sent = store
            try:
                if agree_only:
                    probe, _ = classifier.classify(row["snippet"], f"probe-{session_id}-{i:03d}", lane, store=False)
                    sent = probe == row["expected"]
                if agree_only and not sent:
                    got, request_id = probe, None
                else:
                    # One session per snippet, so Mubit can hold some sessions back as test cases.
                    got, request_id = classifier.classify(row["snippet"], f"{session_id}-{i:03d}", lane, store=store)
            except spend.BudgetExceeded as e:
                print(f"  STOPPED at {i}/{len(rows)}: {e}")
                break
            except Exception as e:
                got, request_id = "error", None
                print(f"  [{i}] error: {type(e).__name__}: {str(e)[:200]}")
            result = {"lane": lane, "snippet": row["snippet"], "expected": row["expected"],
                      "got": got, "request_id": request_id, "recorded": sent}
            results.append(result)
            out.write(json.dumps(result) + "\n")
            mark = "" if sent else "  (not recorded)"
            print(f"  [{i}/{len(rows)}] expected={row['expected']:<24} got={got:<24} id={request_id}{mark}")
    spent = spend.load()["lanes"].get(lane, {}).get("usd", 0.0) - spent_before
    print(f"  wrote {out_path.relative_to(config.ROOT)}; est. spend this run ${spent:.4f}")
    return results



def parse_args(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--lane", choices=[*config.LANES, "all"], default="all")
    parser.add_argument("--dry-run", action="store_true", help="use the offline stub, no network")
    parser.add_argument("--agree-only", action="store_true",
                        help="record a call only where the provider's label matches ours (cleaner training data)")
    parser.add_argument("--split", default=None, help="data file name to send, e.g. seed_extra2")
    parser.add_argument("--extra", action="store_true",
                        help="send data/<lane>/seed_extra.jsonl (more examples for an already-seeded lane)")
    args = parser.parse_args()
    if args.dry_run:
        os.environ["GUARD_OFFLINE"] = "1"
    elif not config.offline() and not config.api_key():
        parser.error("MUBIT_API_KEY is not set (put it in .env)")
    args.lanes = list(config.LANES) if args.lane == "all" else [args.lane]
    return args


if __name__ == "__main__":
    args = parse_args(__doc__)
    split = args.split or ("seed_extra" if args.extra else "seed")
    before = spend.snapshot()
    for lane in args.lanes:
        if not data_path(lane, split).exists():
            print(f"== {lane}: no {split}.jsonl, skipped\n")
            continue
        results = run_batch(lane, split, agree_only=args.agree_only)
        correct = sum(r["got"] == r["expected"] for r in results)
        recorded = [r for r in results if r.get("recorded")]
        flipped = sum(r["got"] != r["expected"] for r in recorded) if args.agree_only else 0
        print(f"  {lane}: {correct}/{len(results)} matched expected, {len(recorded)} recorded"
              + (f", {flipped} recorded answers differed from the check" if args.agree_only else "") + "\n")
    spend.run_summary(before)
